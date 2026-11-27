"""data/task_processor.py — Извлечение метаданных и расчет фаз жизненного цикла задачи."""
from typing import Dict, List, Tuple, Any, Optional
import pandas as pd
from config import (
    ALL_TRACKED_STATUSES,
    STATUS_ANALYTICS_WAIT,
    STATUS_ANALYTICS_WORK,
    STATUS_ANALYTICS_REVIEW,
    STATUS_DEV_WAIT,
    STATUS_DEV_WORK,
    STATUS_DEV_REVIEW,
    STATUS_QA_WAIT,
    STATUS_QA_WORK,
    STATUS_COMPLETION,
    CORE_QA_TEAM,
    CREATION_SIZE_PROJECT,
    TASK_ESTIMATE_PROJECT,
)
from data.workflow import (
    BUDGET_PROJECTS, BUDGET_READY_STATUSES,
    FINANCE_ACTIVE_STATUSES, FINANCE_EXTRA_STATUSES, FINANCE_PROJECT, FINANCE_STATUS_MAP,
    READY_AT, READY_CYCLE, READY_LEAD, READY_STAGE_COLUMNS, READY_STATUS, RELEASED_AT,
    RELEASE_WAIT, STANDARD_STATUS_FIELDS, msfo_release_transitions,
)
from utils.time_calc import get_work_minutes


def clean_val(raw: Any) -> str:
    if pd.isna(raw):
        return ""
    return str(raw).strip("[]'\" ").strip()


def extract_task_type(task_df: pd.DataFrame) -> str:
    sub = task_df[task_df['changed_value'].astype(str).str.lower().isin(['type', 'тип задачи в проекте', 'тип работы'])].copy()
    if sub.empty:
        return "Не определен"
    sub['clean_val'] = sub['added_values'].apply(clean_val)
    sub = sub[sub['clean_val'] != '']
    if sub.empty:
        return "Не определен"
    latest = sub.sort_values('timestamp').iloc[-1]['clean_val'].lower()
    
    if latest in ['bug', 'баг']:
        return "Дефект"
    if latest in ['task', 'задача', 'change', 'задача осфс']:
        return "Фича / Задача"
    if latest in ['epic', 'эпик']:
        return "Эпик"
    if latest in ['техдолг']:
        return "Техдолг"
    if latest in ['run']:
        return "Эксплуатация"
    return latest


def extract_task_priorities(task_df: pd.DataFrame) -> Dict[str, str]:
    p_sub = task_df[task_df['changed_value'].astype(str).str.contains('Приоритет по задаче|Priority', case=False, na=False)].copy()
    priority_val = "Не указан"
    if not p_sub.empty:
        p_sub['clean'] = p_sub['added_values'].apply(clean_val)
        p_sub = p_sub[p_sub['clean'] != '']
        if not p_sub.empty:
            latest_p = p_sub.sort_values('timestamp').iloc[-1]['clean']
            mapping = {
                'Блокирующий': 'Блокирующий',
                'Критичный': 'Критичный', 'Critical': 'Критичный',
                'Важный': 'Важный', 'Major': 'Важный',
                'Обычный': 'Обычный', 'Normal': 'Обычный',
                'Низкий': 'Низкий', 'Minor': 'Низкий'
            }
            priority_val = mapping.get(latest_p, latest_p)

    q_sub = task_df[task_df['changed_value'] == 'Приоритет в очереди'].copy()
    queue_rank = "Не задан"
    if not q_sub.empty:
        q_sub['clean'] = q_sub['added_values'].apply(clean_val)
        q_sub = q_sub[q_sub['clean'] != '']
        if not q_sub.empty:
            queue_rank = q_sub.sort_values('timestamp').iloc[-1]['clean']

    return {"Приоритет": priority_val, "Ранг в очереди": queue_rank}


def extract_task_estimates(
    task_df: pd.DataFrame, *, project: str = "", first_task_size: bool = False
) -> dict[str, str | int]:
    est: dict[str, str | int] = {
        "an_plan": "", "an_fact": "",
        "dev_plan": "", "dev_fact": "",
        "qa_plan": "", "qa_fact": "",
        "task_size": ""
    }
    if project == CREATION_SIZE_PROJECT:
        size_events = task_df["changed_value"].eq("Size")
        if not first_task_size:
            size_events &= task_df["activity_type"].eq("IssueCreatedActivityItem")
        sizes = (
            task_df.loc[size_events, ["timestamp", "added_values"]]
            .sort_values("timestamp", kind="stable")["added_values"]
            .map(clean_val)
        )
        if first_task_size:
            sizes = sizes[sizes.ne("")].str.upper()
            est["task_size_changes"] = max(0, int(sizes.ne(sizes.shift()).sum()) - 1)
        if not sizes.empty:
            est["task_size"] = sizes.iloc[0]
        return est

    sub = task_df[task_df['changed_value'].astype(str).str.contains('оценка|size|storypoints', case=False, na=False)].copy()
    if sub.empty:
        return est
    if project == TASK_ESTIMATE_PROJECT:
        fields = sub["changed_value"].str.strip().str.lower()
        size_field = "оценка задачи" if fields.eq("оценка задачи").any() else "size"

    sub['clean_val'] = sub['added_values'].apply(clean_val)
    sub = sub[sub['clean_val'] != '']
    if sub.empty:
        return est

    for _, row in sub.sort_values('timestamp').iterrows():
        cv = str(row['changed_value']).strip().lower()
        val = row['clean_val']
        if 'аналитик' in cv:
            if 'план' in cv:
                est['an_plan'] = val
            elif 'факт' in cv:
                est['an_fact'] = val
        elif 'разработ' in cv:
            if 'план' in cv:
                est['dev_plan'] = val
            elif 'факт' in cv:
                est['dev_fact'] = val
        elif 'тестиров' in cv:
            if 'план' in cv:
                est['qa_plan'] = val
            elif 'факт' in cv:
                est['qa_fact'] = val
        elif 'storypoints' in cv:
            if 'аналитик' in cv and 'факт' in cv:
                est['an_fact'] = val
            elif 'разработ' in cv and 'факт' in cv:
                est['dev_fact'] = val
            elif 'тестиров' in cv and 'факт' in cv:
                est['qa_fact'] = val
        elif project == TASK_ESTIMATE_PROJECT:
            if cv == size_field:
                est["task_size"] = val
        elif 'оценка задачи' in cv or 'size' in cv:
            est['task_size'] = val
    return est


def extract_task_deadlines(task_df: pd.DataFrame, finished_at: Optional[pd.Timestamp]) -> Dict[str, Any]:
    deadline_sub = task_df[task_df['changed_value'] == 'Дедлайн заказчика'].copy()
    deadline_sub['clean'] = deadline_sub['added_values'].apply(clean_val)
    deadline_sub = deadline_sub[deadline_sub['clean'] != '']
    
    deadline_history = []
    for _, r in deadline_sub.sort_values('timestamp').iterrows():
        try:
            ms = int(r['clean'])
            dt = pd.to_datetime(ms, unit='ms')
            deadline_history.append((r['timestamp'], dt))
        except Exception:
            pass

    if not deadline_history:
        return {
            "has_deadline": False, "first_deadline": None, "final_deadline": None,
            "deadline_shifts": 0, "deadline_slippage_days": 0, "sla_status": "Без дедлайна",
            "delay_days": 0, "finished_at": finished_at
        }

    first_deadline = deadline_history[0][1]
    final_deadline = deadline_history[-1][1]
    shifts = max(0, len(deadline_history) - 1)
    slippage_days = (final_deadline.date() - first_deadline.date()).days

    today = pd.Timestamp.now()
    if finished_at is not None:
        delay = (finished_at.date() - final_deadline.date()).days
        sla_status = "В срок" if delay <= 0 else "С опозданием"
    else:
        delay = (today.date() - final_deadline.date()).days
        sla_status = "В работе (в графике)" if delay <= 0 else "В работе (просрочено)"

    return {
        "has_deadline": True, "first_deadline": first_deadline, "final_deadline": final_deadline,
        "deadline_shifts": shifts, "deadline_slippage_days": max(0, slippage_days),
        "sla_status": sla_status, "delay_days": delay, "finished_at": finished_at
    }


def process_single_task(
    task_id: str,
    task_df: pd.DataFrame,
    work_start_h: int = 9,
    work_end_h: int = 18,
    net_ratio: float = 0.78,
    net_day_hours: float = 7.0,
    *,
    core_qa: tuple[str, ...] = tuple(CORE_QA_TEAM),
    first_task_size: bool = False,
    msfo_release: bool = False,
) -> Tuple[Dict[str, Any], List[dict], List[dict], List[dict], List[dict], List[dict], List[dict], List[dict]]:
    """Обрабатывает всю историю задачи и вычисляет длительности по статусам и итерациям."""
    project = task_id.rpartition("-")[0]
    is_finance = project == FINANCE_PROJECT
    status_fields = STANDARD_STATUS_FIELDS
    if is_finance and task_df["changed_value"].eq("Stage").any():
        status_fields = ("Stage",)
    status_df = task_df[task_df["changed_value"].isin(status_fields)].copy()
    status_df["timestamp"] = pd.to_datetime(status_df["timestamp"])
    status_df = status_df.sort_values("timestamp", kind="stable").reset_index(drop=True)
    status_df["from_status"] = status_df["removed_values"].apply(clean_val)
    status_df["to_status"] = status_df["added_values"].apply(clean_val)
    if is_finance:
        for column in ("from_status", "to_status"):
            status_df[column] = status_df[column].map(
                lambda status: FINANCE_STATUS_MAP.get(status.casefold(), status)
            )

    tracked_statuses = ALL_TRACKED_STATUSES + list(FINANCE_EXTRA_STATUSES) if is_finance else ALL_TRACKED_STATUSES
    status_times = dict.fromkeys(tracked_statuses, 0.0)
    qa_in_test_intervals = []
    qa_waiting_intervals = []

    qa_iters, dev_iters, an_iters = [], [], []
    qa_wait_iters = []
    dev_revs, an_revs, reworks = [], [], []

    qa_first_wait = None
    def first_status_time(statuses, until=None):
        matching = status_df["to_status"].isin(statuses)
        if until is not None:
            matching &= status_df["timestamp"].le(until)
        dates = status_df.loc[matching, "timestamp"]
        return None if dates.empty else dates.iloc[0]

    def duration_days(start, end):
        if start is None or end is None:
            return None
        return get_work_minutes(start, end, work_start_h, work_end_h, net_ratio) / 60 / net_day_hours

    ready_statuses = (READY_STATUS, *BUDGET_READY_STATUSES) if project in BUDGET_PROJECTS else (READY_STATUS,)
    ready_at = first_status_time(ready_statuses)
    if msfo_release:
        extra_ready_dates = status_df.loc[msfo_release_transitions(status_df), "timestamp"]
        if not extra_ready_dates.empty and (ready_at is None or extra_ready_dates.iloc[0] < ready_at):
            ready_at = extra_ready_dates.iloc[0]
    analytics_started = first_status_time(STATUS_ANALYTICS_WAIT + STATUS_ANALYTICS_WORK, ready_at)
    lead_days = duration_days(analytics_started, ready_at)
    active_statuses = STATUS_ANALYTICS_WORK + STATUS_DEV_WORK + STATUS_QA_WORK
    if is_finance:
        active_statuses += list(FINANCE_ACTIVE_STATUSES)
    ready_cycle_days = duration_days(first_status_time(active_statuses, ready_at), ready_at)

    if is_finance:
        task_finished_at = ready_at
        exits_qa = (
            status_df["from_status"].isin(STATUS_QA_WORK)
            & ~status_df["to_status"].isin(STATUS_QA_WAIT + STATUS_QA_WORK)
        )
        if ready_at is not None:
            exits_qa &= status_df["timestamp"].le(ready_at)
        qa_exits = status_df.loc[exits_qa, "timestamp"]
        qa_final_tested = None if qa_exits.empty else qa_exits.iloc[-1]
    else:
        task_finished_at = first_status_time(STATUS_COMPLETION)
        qa_final_tested = first_status_time(("Протестировано",))
        resolved_sub = task_df[task_df["activity_type"].eq("IssueResolvedActivityItem")]
        if not resolved_sub.empty:
            r_time = pd.to_datetime(resolved_sub.iloc[0]["timestamp"])
            if task_finished_at is None or r_time < task_finished_at:
                task_finished_at = r_time

    cycle_days = duration_days(first_status_time(active_statuses, task_finished_at), task_finished_at)
    released_at = first_status_time(("Зарелизили",)) if is_finance else None
    release_wait = (
        duration_days(ready_at, released_at)
        if ready_at is not None and released_at is not None and ready_at <= released_at
        else None
    )
    stage_days = dict.fromkeys(READY_STAGE_COLUMNS, 0.0)
    lead_active_days = 0.0

    # Добавляем финальный интервал до завершения, чтобы не терять время в последнем статусе
    intervals = []
    for i in range(len(status_df) - 1):
        intervals.append((status_df.iloc[i], status_df.iloc[i + 1]["timestamp"]))
    if len(status_df) > 0 and task_finished_at is not None and task_finished_at > status_df.iloc[-1]["timestamp"]:
        intervals.append((status_df.iloc[-1], task_finished_at))

    qa_num = dev_num = an_num = 1
    for r_curr, t2 in intervals:
        t1 = r_curr["timestamp"]
        curr_status = r_curr["to_status"]
        dur_mins = get_work_minutes(t1, t2, work_start_h, work_end_h, net_ratio)
        dur_days = round((dur_mins / 60.0) / net_day_hours, 2)
        author = clean_val(r_curr.get("author_full_name", "Не указан")) or "Не указан"

        if curr_status in status_times:
            status_times[curr_status] += dur_mins

        if ready_at is not None and t1 < ready_at:
            interval_days = dur_mins / 60 / net_day_hours
            if curr_status in stage_days:
                stage_days[curr_status] += interval_days
            if is_finance and analytics_started is not None and t1 >= analytics_started and curr_status in active_statuses:
                lead_active_days += interval_days


        if curr_status == "В аналитике":
            an_iters.append({
                "Задача": task_id, "Итерация": f"#{an_num}", "Аналитик": author,
                "Начало": t1.strftime("%Y-%m-%d %H:%M:%S"), "Завершение": t2.strftime("%Y-%m-%d %H:%M:%S"),
                "Раб. дней": dur_days,
            })
            an_num += 1

        elif curr_status in STATUS_ANALYTICS_REVIEW:
            an_revs.append({
                "Задача": task_id, "Этап ревью": curr_status, "Ревьюер / Исполнитель": author,
                "Начало": t1.strftime("%Y-%m-%d %H:%M:%S"), "Завершение": t2.strftime("%Y-%m-%d %H:%M:%S"),
                "Длительность (д.)": dur_days,
            })

        elif curr_status == "В разработке":
            dev_iters.append({
                "Задача": task_id, "Итерация": f"#{dev_num}", "Разработчик": author,
                "Начало": t1.strftime("%Y-%m-%d %H:%M:%S"), "Завершение": t2.strftime("%Y-%m-%d %H:%M:%S"),
                "Раб. дней": dur_days,
            })
            dev_num += 1

        elif curr_status in STATUS_DEV_REVIEW:
            dev_revs.append({
                "Задача": task_id, "Этап ревью": curr_status, "Ревьюер / Разработчик": author,
                "Начало": t1.strftime("%Y-%m-%d %H:%M:%S"), "Завершение": t2.strftime("%Y-%m-%d %H:%M:%S"),
                "Длительность (д.)": dur_days,
            })

        elif curr_status == "К тестированию":
            if qa_first_wait is None:
                qa_first_wait = t1
            qa_waiting_intervals.append((t1, t2))
            qa_wait_iters.append({
                "Задача": task_id, "Начало": t1.strftime("%Y-%m-%d %H:%M:%S"),
                "Завершение": t2.strftime("%Y-%m-%d %H:%M:%S"), "Раб. дней": dur_days,
            })

        elif curr_status == "В тестировании":
            qa_in_test_intervals.append((t1, t2))
            role_type = "Основной QA" if any(qa.lower() in author.lower() for qa in core_qa) else "Помогающая роль"
            qa_iters.append({
                "Задача": task_id, "Итерация": f"#{qa_num}", "Исполнитель": author, "Роль": role_type,
                "Начало": t1.strftime("%Y-%m-%d %H:%M:%S"), "Завершение": t2.strftime("%Y-%m-%d %H:%M:%S"),
                "Раб. дней": dur_days,
            })
            qa_num += 1

    # Детекция возвратов на доработку (reworks)
    for i in range(len(status_df) - 1):
        r_c = status_df.iloc[i]
        if r_c["from_status"] == "В тестировании" and r_c["to_status"] == "К разработке":
            qa_rejector = clean_val(r_c.get("author_full_name", ""))
            t_back, dev_fixer = None, "Не определен"
            for j in range(i + 1, len(status_df)):
                cand = status_df.iloc[j]
                if cand["to_status"] in ["В разработке", "К тестированию"]:
                    c_auth = clean_val(cand.get("author_full_name", ""))
                    if c_auth and not any(qa.lower() in c_auth.lower() for qa in core_qa):
                        dev_fixer = c_auth
                if cand["to_status"] == "К тестированию":
                    t_back = cand["timestamp"]
                    break
            if t_back and t_back > r_c["timestamp"]:
                fix_mins = get_work_minutes(r_c["timestamp"], t_back, work_start_h, work_end_h, net_ratio)
                reworks.append({
                    "Задача": task_id, "Разработчик (исправил)": dev_fixer, "Кто вернул": qa_rejector,
                    "Дата возврата": r_c["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                    "Возвращено в QA": t_back.strftime("%Y-%m-%d %H:%M:%S"),
                    "Время фикса (д.)": round((fix_mins / 60.0) / net_day_hours, 2),
                })

    # Сводные метрики по направлениям
    mins_test_qa = sum(get_work_minutes(s, e, work_start_h, work_end_h, net_ratio) for s, e in qa_in_test_intervals)
    mins_wait_qa = sum(get_work_minutes(s, e, work_start_h, work_end_h, net_ratio) for s, e in qa_waiting_intervals)
    mins_cycle_qa = (
        get_work_minutes(qa_first_wait, qa_final_tested, work_start_h, work_end_h, net_ratio)
        if (qa_first_wait and qa_final_tested) else (mins_test_qa + mins_wait_qa)
    )
    h_test_qa = mins_test_qa / 60.0
    h_wait_qa = mins_wait_qa / 60.0
    h_total_qa = mins_cycle_qa / 60.0
    h_other_qa = max(0.0, h_total_qa - (h_test_qa + h_wait_qa))
    flow_eff_qa = (h_test_qa / h_total_qa * 100) if h_total_qa > 0 else 0.0

    task_row = {
        "Задача": task_id,
        "Сквозной Cycle Time (д.)": round(cycle_days, 2) if cycle_days is not None else None,
        READY_AT: ready_at,
        READY_LEAD: round(lead_days, 2) if lead_days is not None else None,
        READY_CYCLE: round(ready_cycle_days, 2) if ready_cycle_days is not None else None,
        **{column: round(stage_days[status], 2) for status, column in READY_STAGE_COLUMNS.items()},
        "В тестировании (дни)": round(h_test_qa / net_day_hours, 2),
        "Очередь ожидания QA (дни)": round(h_wait_qa / net_day_hours, 2),
        "Циклтайм QA (дни)": round(h_total_qa / net_day_hours, 2),
        "Доработки у dev (дни)": round(h_other_qa / net_day_hours, 2),
        "Итераций QA": len(qa_in_test_intervals),
        "Flow Efficiency QA (%)": round(flow_eff_qa, 1),
    }

    for st_name, mins in status_times.items():
        task_row[f"{st_name} (д.)"] = round((mins / 60.0) / net_day_hours, 2)

    # Агрегаты аналитики и разработки
    an_wait = task_row.get("К аналитике (д.)", 0.0)
    an_work = task_row.get("В аналитике (д.)", 0.0)
    an_rev = sum(task_row.get(f"{s} (д.)", 0.0) for s in STATUS_ANALYTICS_REVIEW)
    an_cycle = an_wait + an_work + an_rev
    task_row["Цикл Аналитики (д.)"] = round(an_cycle, 2)
    task_row["Очередь/Ревью Аналитики (д.)"] = round(an_wait + an_rev, 2)
    task_row["Flow Аналитики (%)"] = round((an_work / an_cycle * 100) if an_cycle > 0 else 0.0, 1)

    dev_wait = task_row.get("К разработке (д.)", 0.0)
    dev_work = task_row.get("В разработке (д.)", 0.0)
    dev_rev = sum(task_row.get(f"{s} (д.)", 0.0) for s in STATUS_DEV_REVIEW)
    dev_cycle = dev_wait + dev_work + dev_rev
    task_row["Цикл Разработки (д.)"] = round(dev_cycle, 2)
    task_row["Очередь/Код Ревью Dev (д.)"] = round(dev_wait + dev_rev, 2)
    task_row["Flow Разработки (%)"] = round((dev_work / dev_cycle * 100) if dev_cycle > 0 else 0.0, 1)

    # Сквозной поток
    tot_active = an_work + dev_work + (h_test_qa / net_day_hours)
    tot_wait = (an_wait + an_rev) + (dev_wait + dev_rev) + (h_wait_qa / net_day_hours) + (h_other_qa / net_day_hours)
    full_lead = tot_active + tot_wait
    if is_finance:
        full_lead = lead_days
        tot_active = lead_active_days if lead_days is not None else None
        tot_wait = max(0, lead_days - lead_active_days) if lead_days is not None else None
        task_row[RELEASED_AT] = released_at
        task_row[RELEASE_WAIT] = round(release_wait, 2) if release_wait is not None else None
    task_row["Полный Lead Time (д.)"] = round(full_lead, 2) if full_lead is not None else None
    task_row["Всего очередей (д.)"] = round(tot_wait, 2) if tot_wait is not None else None
    task_row["Чистая работа (д.)"] = round(tot_active, 2) if tot_active is not None else None
    task_row["Сквозной Flow Efficiency (%)"] = round((tot_active / full_lead * 100) if full_lead else 0.0, 1)

    # Метаданные
    task_row["Тип задачи"] = extract_task_type(task_df)
    task_row.update(extract_task_priorities(task_df))
    task_row.update(extract_task_estimates(task_df, project=project, first_task_size=first_task_size))
    task_row.update(extract_task_deadlines(task_df, task_finished_at))

    return (
        task_row,
        qa_iters,
        dev_iters,
        an_iters,
        dev_revs,
        an_revs,
        reworks,
        qa_wait_iters,
    )
