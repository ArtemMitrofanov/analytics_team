import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from crewai import Agent, Crew, LLM, Process, Task

st.set_page_config(
    page_title="Team Process Analytics | End-to-End Delivery & Quarters",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Комплексный процессный аудит команды")
st.caption(
    "Сквозная процессная аналитика: Месячные спринты, Кварталы, Оценки, Дедлайны, Типы и Приоритеты"
)

# --- Список штатных тестировщиков ---
CORE_QA_TEAM = [
    "Крохалева Татьяна Владимировна",
    "Митрофанов Артём",
    "Стрелок Наталья Владимировна",
    "Островская Татьяна Евгеньевна",
]

MONTH_NAMES_RU = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
}

TSHIRT_ORDER = ["XS", "S", "M", "L", "XL"]
PRIORITY_ORDER = ["Блокирующий", "Критичный", "Важный", "Обычный", "Низкий", "Не указан"]

# Статусы по этапам
STATUS_ANALYTICS_WAIT = ["К аналитике"]
STATUS_ANALYTICS_WORK = ["В аналитике"]
STATUS_ANALYTICS_REVIEW = ["К ревью (аналитика)", "Ревью аналитики"]

STATUS_DEV_WAIT = ["К разработке"]
STATUS_DEV_WORK = ["В разработке"]
STATUS_DEV_REVIEW = ["К ревью (разработка)", "Код ревью"]

STATUS_QA_WAIT = ["К тестированию"]
STATUS_QA_WORK = ["В тестировании"]

ALL_TRACKED_STATUSES = (
    STATUS_ANALYTICS_WAIT
    + STATUS_ANALYTICS_WORK
    + STATUS_ANALYTICS_REVIEW
    + STATUS_DEV_WAIT
    + STATUS_DEV_WORK
    + STATUS_DEV_REVIEW
    + STATUS_QA_WAIT
    + STATUS_QA_WORK
)

# --- Боковая панель: Конфигурация ---
with st.sidebar:
    st.header("⚙️ Параметры анализа")
    gemini_key = st.text_input(
        "Gemini API Key (из Google AI Studio)", type="password"
    )

    st.markdown("---")
    st.subheader("🗓️ График работы")
    work_start_h = st.number_input("Начало дня (час)", 0, 23, 9)
    work_end_h = st.number_input("Конец дня (час)", 0, 23, 18)
    deduct_hours = st.number_input("Обед + созвоны (часов)", 0.0, 8.0, 2.0)

    day_window = max(1.0, float(work_end_h - work_start_h))
    net_day_hours = max(1.0, day_window - deduct_hours)
    net_ratio = net_day_hours / day_window

    st.info(f"Эффективный день: **{net_day_hours:.1f} ч.** (коэф. {net_ratio:.2f})")

    st.markdown("---")
    st.subheader("🎯 Фильтры выборки")
    only_qa_active = st.checkbox(
        "Учитывать только задачи с QA (> 0 д.)",
        value=True,
        help="Для сводных KPI в разделе QA отсекает задачи без этапа тестирования",
    )

    st.markdown("---")
    with st.expander("👥 Список профильных QA"):
        for qa_name in CORE_QA_TEAM:
            st.markdown(f"- {qa_name}")


# --- Расчет рабочих минут ---
def get_work_minutes(s_dt: pd.Timestamp, e_dt: pd.Timestamp, start_h: int, end_h: int, ratio: float) -> float:
    if s_dt >= e_dt:
        return 0.0
    mins = 0.0
    cur = s_dt
    while cur.date() <= e_dt.date():
        if cur.weekday() < 5:  # Будни (пн-пт)
            d_start = pd.Timestamp(year=cur.year, month=cur.month, day=cur.day, hour=start_h, minute=0)
            d_end = pd.Timestamp(year=cur.year, month=cur.month, day=cur.day, hour=end_h, minute=0)
            overlap_start = max(cur, d_start)
            overlap_end = min(e_dt, d_end)
            if overlap_end > overlap_start:
                mins += ((overlap_end - overlap_start).total_seconds() / 60.0) * ratio
        cur = pd.Timestamp(year=cur.year, month=cur.month, day=cur.day) + pd.Timedelta(days=1)
    return mins


# --- Извлечение типа задачи ---
def extract_task_type(task_df: pd.DataFrame) -> str:
    sub = task_df[task_df['changed_value'].astype(str).str.lower().isin(['type', 'тип задачи в проекте', 'тип работы'])].copy()
    if sub.empty:
        return "Не определен"
    sub['clean_val'] = sub['added_values'].astype(str).str.strip("[]'\" ").str.strip()
    sub = sub[sub['clean_val'] != '']
    if sub.empty:
        return "Не определен"
    sub['timestamp'] = pd.to_datetime(sub['timestamp'])
    sub = sub.sort_values('timestamp')
    latest = sub.iloc[-1]['clean_val']
    
    l_lower = latest.lower()
    if l_lower in ['bug', 'баг']:
        return "Дефект (Bug)"
    elif l_lower in ['task', 'задача', 'change', 'задача осфс']:
        return "Фича / Задача (Task)"
    elif l_lower in ['epic', 'эпик']:
        return "Эпик (Epic)"
    elif l_lower in ['техдолг']:
        return "Техдолг"
    elif l_lower in ['run']:
        return "Эксплуатация (Run)"
    else:
        return latest


# --- Извлечение приоритетов задачи ---
def extract_task_priorities(task_df: pd.DataFrame):
    p_sub = task_df[task_df['changed_value'].astype(str).str.contains('Приоритет по задаче|Priority', case=False, na=False)].copy()
    priority_val = "Не указан"
    if not p_sub.empty:
        p_sub['clean'] = p_sub['added_values'].astype(str).str.strip("[]'\" ").str.strip()
        p_sub = p_sub[p_sub['clean'] != '']
        if not p_sub.empty:
            p_sub['timestamp'] = pd.to_datetime(p_sub['timestamp'])
            p_sub = p_sub.sort_values('timestamp')
            latest_p = p_sub.iloc[-1]['clean']
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
        q_sub['clean'] = q_sub['added_values'].astype(str).str.strip("[]'\" ").str.strip()
        q_sub = q_sub[q_sub['clean'] != '']
        if not q_sub.empty:
            q_sub['timestamp'] = pd.to_datetime(q_sub['timestamp'])
            q_sub = q_sub.sort_values('timestamp')
            queue_rank = q_sub.iloc[-1]['clean']

    return {
        "Приоритет": priority_val,
        "Ранг в очереди": queue_rank
    }


# --- Извлечение оценок задачи ---
def extract_task_estimates(task_df: pd.DataFrame):
    est = {
        "an_plan": "", "an_fact": "",
        "dev_plan": "", "dev_fact": "",
        "qa_plan": "", "qa_fact": "",
        "task_size": ""
    }
    sub = task_df[task_df['changed_value'].astype(str).str.contains('оценка|size|storypoints', case=False, na=False)].copy()
    if sub.empty:
        return est
    
    sub['clean_val'] = sub['added_values'].astype(str).str.strip("[]'\" ").str.strip()
    sub = sub[sub['clean_val'] != '']
    sub['timestamp'] = pd.to_datetime(sub['timestamp'])
    sub = sub.sort_values('timestamp')

    for _, row in sub.iterrows():
        cv = str(row['changed_value']).lower()
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
        elif 'оценка задачи' in cv or 'size' in cv:
            est['task_size'] = val

    return est


# --- Анализ дедлайнов задачи ---
def extract_task_deadlines(task_df: pd.DataFrame, finished_at: pd.Timestamp):
    deadline_sub = task_df[task_df['changed_value'] == 'Дедлайн заказчика'].copy()
    deadline_sub['clean'] = deadline_sub['added_values'].astype(str).str.strip("[]'\" ").str.strip()
    deadline_sub = deadline_sub[deadline_sub['clean'] != '']
    deadline_sub['timestamp'] = pd.to_datetime(deadline_sub['timestamp'])
    deadline_sub = deadline_sub.sort_values('timestamp')

    deadline_history = []
    for _, r in deadline_sub.iterrows():
        try:
            ms = int(r['clean'])
            dt = pd.to_datetime(ms, unit='ms')
            deadline_history.append((r['timestamp'], dt))
        except Exception:
            pass

    if not deadline_history:
        return {
            "has_deadline": False,
            "first_deadline": None,
            "final_deadline": None,
            "deadline_shifts": 0,
            "deadline_slippage_days": 0,
            "sla_status": "Без дедлайна",
            "delay_days": 0,
            "finished_at": finished_at
        }

    first_deadline = deadline_history[0][1]
    final_deadline = deadline_history[-1][1]
    shifts = max(0, len(deadline_history) - 1)
    slippage_days = (final_deadline.date() - first_deadline.date()).days

    today = pd.Timestamp.now()

    if finished_at is not None:
        delay = (finished_at.date() - final_deadline.date()).days
        if delay <= 0:
            sla_status = "В срок (On-Time)"
        else:
            sla_status = "С опозданием (Overdue)"
    else:
        delay = (today.date() - final_deadline.date()).days
        if delay <= 0:
            sla_status = "В работе (в графике)"
        else:
            sla_status = "В работе (просрочено)"

    return {
        "has_deadline": True,
        "first_deadline": first_deadline,
        "final_deadline": final_deadline,
        "deadline_shifts": shifts,
        "deadline_slippage_days": max(0, slippage_days),
        "sla_status": sla_status,
        "delay_days": delay,
        "finished_at": finished_at
    }


# --- Обработка истории по задаче ---
def process_single_task(task_id: str, task_df: pd.DataFrame):
    status_df = task_df[task_df["changed_value"] == "Текущий статус"].copy()
    status_df["timestamp"] = pd.to_datetime(status_df["timestamp"])
    status_df = status_df.sort_values("timestamp").reset_index(drop=True)

    status_df["from_status"] = status_df["removed_values"].astype(str).str.strip("[]'\"")
    status_df["to_status"] = status_df["added_values"].astype(str).str.strip("[]'\"")

    status_times = {st: 0.0 for st in ALL_TRACKED_STATUSES}
    qa_in_test_intervals = []
    qa_waiting_intervals = []

    qa_iterations_records = []
    dev_iterations_records = []
    an_iterations_records = []

    dev_reviews_records = []
    an_reviews_records = []
    qa_reworks_records = []

    qa_first_wait = None
    qa_final_tested = None
    task_finished_at = None
    qa_iter_num = dev_iter_num = an_iter_num = 1
    dev_rev_num = an_rev_num = 1

    completion_statuses = ["Протестировано", "К релизу", "Релиз (установка доработок на боевой)", "Завершено"]

    for i in range(len(status_df) - 1):
        r_curr = status_df.iloc[i]
        r_next = status_df.iloc[i + 1]
        t1, t2 = r_curr["timestamp"], r_next["timestamp"]
        curr_status = r_curr["to_status"]
        dur_mins = get_work_minutes(t1, t2, work_start_h, work_end_h, net_ratio)
        dur_days = round((dur_mins / 60.0) / net_day_hours, 2)
        author_name = str(r_curr.get("author_full_name", "Не указан")).strip()
        if not author_name or author_name == "nan":
            author_name = "Не указан"

        if curr_status in status_times:
            status_times[curr_status] += dur_mins

        if curr_status in completion_statuses and task_finished_at is None:
            task_finished_at = t1

        # 1. Аналитика
        if curr_status == "В аналитике":
            an_iterations_records.append({
                "Задача": task_id,
                "Итерация": f"#{an_iter_num}",
                "Аналитик": author_name,
                "Начало": t1.strftime("%Y-%m-%d %H:%M:%S"),
                "Завершение": t2.strftime("%Y-%m-%d %H:%M:%S"),
                "Статус после": r_next["to_status"],
                "Раб. дней": dur_days,
            })
            an_iter_num += 1

        if curr_status in STATUS_ANALYTICS_REVIEW:
            an_reviews_records.append({
                "Задача": task_id,
                "Этап ревью": curr_status,
                "Ревьюер / Исполнитель": author_name,
                "Начало": t1.strftime("%Y-%m-%d %H:%M:%S"),
                "Завершение": t2.strftime("%Y-%m-%d %H:%M:%S"),
                "Статус после": r_next["to_status"],
                "Длительность (д.)": dur_days,
            })
            an_rev_num += 1

        # 2. Разработка
        if curr_status == "В разработке":
            dev_iterations_records.append({
                "Задача": task_id,
                "Итерация": f"#{dev_iter_num}",
                "Разработчик": author_name,
                "Начало": t1.strftime("%Y-%m-%d %H:%M:%S"),
                "Завершение": t2.strftime("%Y-%m-%d %H:%M:%S"),
                "Статус после": r_next["to_status"],
                "Раб. дней": dur_days,
            })
            dev_iter_num += 1

        if curr_status in STATUS_DEV_REVIEW:
            dev_reviews_records.append({
                "Задача": task_id,
                "Этап ревью": curr_status,
                "Ревьюер / Разработчик": author_name,
                "Начало": t1.strftime("%Y-%m-%d %H:%M:%S"),
                "Завершение": t2.strftime("%Y-%m-%d %H:%M:%S"),
                "Статус после": r_next["to_status"],
                "Длительность (д.)": dur_days,
            })
            dev_rev_num += 1

        # 3. QA
        if curr_status == "К тестированию" and qa_first_wait is None:
            qa_first_wait = t1
        if curr_status == "К тестированию":
            qa_waiting_intervals.append((t1, t2))

        if curr_status == "В тестировании":
            qa_in_test_intervals.append((t1, t2))
            role_type = (
                "Основной QA"
                if any(core_qa.lower() in author_name.lower() for core_qa in CORE_QA_TEAM)
                else "Помогающая роль"
            )
            qa_iterations_records.append({
                "Задача": task_id,
                "Итерация": f"#{qa_iter_num}",
                "Исполнитель": author_name,
                "Роль": role_type,
                "Начало": t1.strftime("%Y-%m-%d %H:%M:%S"),
                "Завершение": t2.strftime("%Y-%m-%d %H:%M:%S"),
                "Статус после": r_next["to_status"],
                "Раб. дней": dur_days,
            })
            qa_iter_num += 1
            if r_next["to_status"] == "Протестировано":
                qa_final_tested = t2
                if task_finished_at is None:
                    task_finished_at = t2

        # 4. Доработки
        if r_curr["from_status"] == "В тестировании" and curr_status == "К разработке":
            qa_rejector = author_name
            t_back = None
            dev_fixer = "Не определен"
            for j in range(i + 1, len(status_df)):
                cand = status_df.iloc[j]
                if cand["to_status"] in ["В разработке", "К тестированию"]:
                    c_auth = str(cand.get("author_full_name", "")).strip()
                    if c_auth and c_auth != "nan" and not any(qa.lower() in c_auth.lower() for qa in CORE_QA_TEAM):
                        dev_fixer = c_auth
                if cand["to_status"] == "К тестированию":
                    t_back = cand["timestamp"]
                    break
            if t_back and t_back > t1:
                fix_mins = get_work_minutes(t1, t_back, work_start_h, work_end_h, net_ratio)
                qa_reworks_records.append({
                    "Задача": task_id,
                    "Разработчик (исправил)": dev_fixer,
                    "Кто вернул (QA)": qa_rejector,
                    "Дата возврата": t1.strftime("%Y-%m-%d %H:%M:%S"),
                    "Возвращено в QA": t_back.strftime("%Y-%m-%d %H:%M:%S"),
                    "Время фикса (д.)": round((fix_mins / 60.0) / net_day_hours, 2),
                })

    if len(status_df) > 0 and task_finished_at is None:
        last_st = status_df.iloc[-1]["to_status"]
        if last_st in completion_statuses:
            task_finished_at = status_df.iloc[-1]["timestamp"]

    resolved_sub = task_df[task_df['activity_type'] == 'IssueResolvedActivityItem']
    if not resolved_sub.empty:
        r_time = pd.to_datetime(resolved_sub.iloc[0]['timestamp'])
        if task_finished_at is None or r_time < task_finished_at:
            task_finished_at = r_time

    mins_test_qa = sum(get_work_minutes(s, e, work_start_h, work_end_h, net_ratio) for s, e in qa_in_test_intervals)
    mins_wait_qa = sum(get_work_minutes(s, e, work_start_h, work_end_h, net_ratio) for s, e in qa_waiting_intervals)
    mins_cycle_qa = (
        get_work_minutes(qa_first_wait, qa_final_tested, work_start_h, work_end_h, net_ratio)
        if (qa_first_wait and qa_final_tested)
        else (mins_test_qa + mins_wait_qa)
    )
    h_test_qa = mins_test_qa / 60.0
    h_wait_qa = mins_wait_qa / 60.0
    h_total_qa = mins_cycle_qa / 60.0
    h_other_qa = max(0.0, h_total_qa - (h_test_qa + h_wait_qa))
    flow_eff_qa = (h_test_qa / h_total_qa * 100) if h_total_qa > 0 else 0.0

    task_row = {
        "Задача": task_id,
        "В тестировании (дни)": round(h_test_qa / net_day_hours, 2),
        "Очередь ожидания QA (дни)": round(h_wait_qa / net_day_hours, 2),
        "Циклтайм QA (дни)": round(h_total_qa / net_day_hours, 2),
        "Доработки у dev (дни)": round(h_other_qa / net_day_hours, 2),
        "Итераций QA": len(qa_in_test_intervals),
        "Flow Efficiency QA (%)": round(flow_eff_qa, 1),
    }

    for st_name, mins in status_times.items():
        task_row[f"{st_name} (д.)"] = round((mins / 60.0) / net_day_hours, 2)

    # Агрегация аналитики
    an_wait = task_row.get("К аналитике (д.)", 0.0)
    an_work = task_row.get("В аналитике (д.)", 0.0)
    an_rev = sum(task_row.get(f"{s} (д.)", 0.0) for s in STATUS_ANALYTICS_REVIEW)
    an_cycle = an_wait + an_work + an_rev
    task_row["Цикл Аналитики (д.)"] = round(an_cycle, 2)
    task_row["Очередь/Ревью Аналитики (д.)"] = round(an_wait + an_rev, 2)
    task_row["Flow Аналитики (%)"] = round((an_work / an_cycle * 100) if an_cycle > 0 else 0.0, 1)

    # Агрегация разработки
    dev_wait = task_row.get("К разработке (д.)", 0.0)
    dev_work = task_row.get("В разработке (д.)", 0.0)
    dev_rev = sum(task_row.get(f"{s} (д.)", 0.0) for s in STATUS_DEV_REVIEW)
    dev_cycle = dev_wait + dev_work + dev_rev
    task_row["Цикл Разработки (д.)"] = round(dev_cycle, 2)
    task_row["Очередь/Код Ревью Dev (д.)"] = round(dev_wait + dev_rev, 2)
    task_row["Flow Разработки (%)"] = round((dev_work / dev_cycle * 100) if dev_cycle > 0 else 0.0, 1)

    # Сквозной пайплайн
    tot_active = an_work + dev_work + (h_test_qa / net_day_hours)
    tot_wait = (an_wait + an_rev) + (dev_wait + dev_rev) + (h_wait_qa / net_day_hours) + (h_other_qa / net_day_hours)
    full_lead = tot_active + tot_wait
    task_row["Полный Lead Time (д.)"] = round(full_lead, 2)
    task_row["Всего очередей (д.)"] = round(tot_wait, 2)
    task_row["Чистая работа (д.)"] = round(tot_active, 2)
    task_row["Сквозной Flow Efficiency (%)"] = round((tot_active / full_lead * 100) if full_lead > 0 else 0.0, 1)

    # Метаполя
    task_row["Тип задачи"] = extract_task_type(task_df)
    task_row.update(extract_task_priorities(task_df))
    task_row.update(extract_task_estimates(task_df))
    task_row.update(extract_task_deadlines(task_df, task_finished_at))

    return (
        task_row,
        qa_iterations_records,
        dev_iterations_records,
        an_iterations_records,
        dev_reviews_records,
        an_reviews_records,
        qa_reworks_records,
    )


# --- Загрузка файлов ---
uploaded_files = st.file_uploader(
    "Загрузите один или несколько CSV-файлов с задачами",
    type=["csv"],
    accept_multiple_files=True,
)

if uploaded_files:
    dfs = []
    for f in uploaded_files:
        f.seek(0)
        try:
            df_temp = pd.read_csv(f, on_bad_lines="skip", low_memory=False)
        except Exception:
            f.seek(0)
            df_temp = pd.read_csv(f, sep=None, engine="python", on_bad_lines="skip")

        if "iissue_id" in df_temp.columns:
            df_temp["task_identifier"] = df_temp["iissue_id"]
        elif "issue_id" in df_temp.columns:
            df_temp["task_identifier"] = df_temp["issue_id"]
        else:
            df_temp["task_identifier"] = f.name.replace(".csv", "")

        dfs.append(df_temp)

    full_raw_df = pd.concat(dfs, ignore_index=True)
    full_raw_df["timestamp"] = pd.to_datetime(full_raw_df["timestamp"])

    all_raw_unique_tasks = full_raw_df["task_identifier"].dropna().unique()
    global_task_summaries = {}
    for tid in all_raw_unique_tasks:
        sub_df = full_raw_df[full_raw_df["task_identifier"] == tid]
        s_data, _, _, _, _, _, _ = process_single_task(str(tid), sub_df)
        global_task_summaries[str(tid)] = s_data
    global_summary_df = pd.DataFrame(list(global_task_summaries.values()))

    # --- Генерация месячных спринтов и кварталов ---
    periods_m = sorted(full_raw_df["timestamp"].dt.to_period("M").unique())
    sprint_lookup = {}
    monthly_sprints_list = []
    for p in periods_m:
        s_date = p.start_time.date()
        e_date = p.end_time.date()
        month_name = MONTH_NAMES_RU.get(p.month, str(p.month))
        label = f"Спринт: {month_name} {p.year} ({s_date.strftime('%d.%m')} — {e_date.strftime('%d.%m')})"
        short_label = f"{month_name} {p.year}"
        sprint_lookup[label] = (s_date, e_date)
        monthly_sprints_list.append({
            "period_name": short_label,
            "full_label": label,
            "start_date": s_date,
            "end_date": e_date,
            "type": "month"
        })

    periods_q = sorted(full_raw_df["timestamp"].dt.to_period("Q").unique())
    quarter_lookup = {}
    quarter_list = []
    for q in periods_q:
        s_date = q.start_time.date()
        e_date = q.end_time.date()
        label = f"Квартал: Q{q.quarter} {q.year} ({s_date.strftime('%d.%m')} — {e_date.strftime('%d.%m')})"
        short_label = f"Q{q.quarter} {q.year}"
        quarter_lookup[label] = (s_date, e_date)
        quarter_list.append({
            "period_name": short_label,
            "full_label": label,
            "start_date": s_date,
            "end_date": e_date,
            "type": "quarter"
        })

    min_log_date = full_raw_df["timestamp"].min().date()
    max_log_date = full_raw_df["timestamp"].max().date()

    with st.sidebar:
        st.markdown("---")
        st.subheader("🗓️ Границы отчетного периода")

        # По умолчанию выбран "Весь период" (index=0)
        period_mode = st.radio(
            "Группировка периода:",
            options=["Весь период", "По месяцам (Спринты)", "По кварталам", "Пользовательский диапазон"],
            index=0
        )

        if period_mode == "По месяцам (Спринты)":
            selected_period_label = st.selectbox("Выберите спринт:", options=list(sprint_lookup.keys()))
            filter_start_date, filter_end_date = sprint_lookup[selected_period_label]
        elif period_mode == "По кварталам":
            selected_period_label = st.selectbox("Выберите квартал:", options=list(quarter_lookup.keys()))
            filter_start_date, filter_end_date = quarter_lookup[selected_period_label]
        elif period_mode == "Пользовательский диапазон":
            selected_period_label = "Пользовательский диапазон"
            date_range = st.date_input("Укажите диапазон дат", value=(min_log_date, max_log_date), min_value=min_log_date, max_value=max_log_date)
            if isinstance(date_range, tuple) and len(date_range) == 2:
                filter_start_date, filter_end_date = date_range
            else:
                filter_start_date, filter_end_date = min_log_date, max_log_date
        else:
            selected_period_label = "Весь период"
            filter_start_date, filter_end_date = min_log_date, max_log_date

        st.caption(f"Период анализа: **{filter_start_date.strftime('%d.%m.%Y')} — {filter_end_date.strftime('%d.%m.%Y')}**")

    # Привязка задач к выбранному периоду по изменению статуса
    if period_mode == "Весь период":
        unique_tasks = all_raw_unique_tasks
    else:
        status_changes_in_period = full_raw_df[
            (full_raw_df["timestamp"].dt.date >= filter_start_date)
            & (full_raw_df["timestamp"].dt.date <= filter_end_date)
            & (full_raw_df["changed_value"] == "Текущий статус")
        ]
        unique_tasks = status_changes_in_period["task_identifier"].dropna().unique()

    tasks_summaries = []
    qa_iterations = []
    dev_iterations = []
    an_iterations = []
    dev_reviews = []
    an_reviews = []
    qa_reworks = []

    for tid in unique_tasks:
        sub_df = full_raw_df[full_raw_df["task_identifier"] == tid]
        (
            s_data,
            qa_iters,
            dev_iters,
            an_iters,
            dev_revs,
            an_revs,
            reworks,
        ) = process_single_task(str(tid), sub_df)
        tasks_summaries.append(s_data)
        qa_iterations.extend(qa_iters)
        dev_iterations.extend(dev_iters)
        an_iterations.extend(an_iters)
        dev_reviews.extend(dev_revs)
        an_reviews.extend(an_revs)
        qa_reworks.extend(reworks)

    summary_df = pd.DataFrame(tasks_summaries)
    qa_iter_df = pd.DataFrame(qa_iterations)
    dev_iter_df = pd.DataFrame(dev_iterations)
    an_iter_df = pd.DataFrame(an_iterations)
    dev_rev_df = pd.DataFrame(dev_reviews)
    an_rev_df = pd.DataFrame(an_reviews)
    reworks_df = pd.DataFrame(qa_reworks)

    # Безопасный расчет статистик (не падает при отсутствии данных)
    def calc_stats(series):
        if series is None or series.empty:
            return 0.0, 0.0, 0.0, 0
        act = series[series > 0]
        if not act.empty:
            return act.mean(), act.median(), act.quantile(0.85), len(act)
        return 0.0, 0.0, 0.0, 0

    def render_searchable_log(log_df: pd.DataFrame, task_col: str, title: str, csv_name: str, key_suffix: str):
        st.markdown(f"##### 📋 {title}")
        if not log_df.empty and task_col in log_df.columns:
            c1, c2 = st.columns([1, 1])
            with c1:
                search_q = st.text_input(
                    "🔍 Быстрый поиск по задаче:",
                    placeholder="Например: 2280 или KBAInternal",
                    key=f"search_{key_suffix}",
                )
            available = sorted(log_df[task_col].dropna().unique())
            with c2:
                selected_t = st.multiselect(
                    "Выбрать из списка:",
                    options=available,
                    default=[],
                    placeholder="Все задачи (или выберите нужные)",
                    key=f"multi_{key_suffix}",
                )

            filtered = log_df.copy()
            if search_q.strip():
                filtered = filtered[filtered[task_col].astype(str).str.contains(search_q.strip(), case=False, na=False)]
            if selected_t:
                filtered = filtered[filtered[task_col].isin(selected_t)]

            st.caption(f"Найдено записей: **{len(filtered)}** из **{len(log_df)}**")
            st.dataframe(filtered, use_container_width=True, hide_index=True)
            csv_exp = filtered.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 Скачать журнал (CSV)", csv_exp, csv_name, "text/csv", key=f"dl_{key_suffix}")
        else:
            st.info("В выбранном периоде нет записей для этого журнала.")

    st.success(
        f"📅 Выбран период: **{selected_period_label}** | Активных задач с движением: **{len(unique_tasks)}** (из {len(all_raw_unique_tasks)})"
    )

    # Защита от пустого датасета (предотвращает KeyError)
    if summary_df.empty:
        st.warning(
            f"⚠️ В выбранном периоде (**{selected_period_label}**) не зафиксировано ни одного движения/изменения статусов задач. "
            "Пожалуйста, выберите другой спринт/квартал в боковой панели или переключитесь на «Весь период»."
        )
    else:
        # ==================== ВЕРХНИЕ ОСНОВНЫЕ ВКЛАДКИ ====================
        tab_overview, tab_sprints_cmp, tab_estimates, tab_deadlines, tab_types, tab_priorities, tab_qa, tab_dev, tab_an, tab_task = st.tabs([
            "🌐 Общая информация",
            "📅 Сравнение периодов (Спринты / Кварталы)",
            "🎯 Оценка задач",
            "⏰ Контроль дедлайнов (SLA)",
            "🐞 Дефекты vs Фичи",
            "⚡ Приоритеты и Очереди",
            "🧪 Аудит тестирования QA",
            "💻 Аудит разработки",
            "📐 Аудит аналитики",
            "🔍 Детализация по задаче",
        ])

        # ==================================================================
        # 1. ОБЩАЯ ИНФОРМАЦИЯ
        # ==================================================================
        with tab_overview:
            st.subheader("🌐 Сквозная воронка поставки (Аналитика → Разработка → QA)")
            mean_lead, med_lead, p85_lead, _ = calc_stats(summary_df.get("Полный Lead Time (д.)", pd.Series(dtype=float)))
            mean_wait, med_wait, p85_wait, _ = calc_stats(summary_df.get("Всего очередей (д.)", pd.Series(dtype=float)))
            mean_work, med_work, p85_work, _ = calc_stats(summary_df.get("Чистая работа (д.)", pd.Series(dtype=float)))
            mean_flow, med_flow, p85_flow, _ = calc_stats(summary_df.get("Сквозной Flow Efficiency (%)", pd.Series(dtype=float)))

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Сквозной Lead Time", f"{mean_lead:.2f} д.", f"Мед: {med_lead:.2f} | P85: {p85_lead:.2f}")
            m2.metric("Суммарно очередей", f"{mean_wait:.2f} д.", f"Мед: {med_wait:.2f} | P85: {p85_wait:.2f}", delta_color="inverse")
            m3.metric("Чистая работа (An+Dev+QA)", f"{mean_work:.2f} д.", f"Мед: {med_work:.2f} | P85: {p85_work:.2f}")
            m4.metric("Сквозной Flow Efficiency", f"{mean_flow:.1f}%", f"Мед: {med_flow:.1f}% | P85: {p85_flow:.1f}%")

            st.markdown("---")
            st.subheader("Детализация среднего времени по каждому статусу (в днях)")
            status_stats = []
            for st_name in ALL_TRACKED_STATUSES:
                col = f"{st_name} (д.)"
                s = summary_df.get(col, pd.Series(dtype=float))
                mean_v, med_v, p85_v, cnt_v = calc_stats(s)
                phase = "Аналитика" if st_name in STATUS_ANALYTICS_WAIT + STATUS_ANALYTICS_WORK + STATUS_ANALYTICS_REVIEW else ("Разработка" if st_name in STATUS_DEV_WAIT + STATUS_DEV_WORK + STATUS_DEV_REVIEW else "Тестирование")
                cat = "Работа" if st_name in STATUS_ANALYTICS_WORK + STATUS_DEV_WORK + STATUS_QA_WORK else "Очередь / Ревью"
                status_stats.append({
                    "Этап": phase, "Тип": cat, "Статус": st_name,
                    "Среднее (д.)": round(mean_v, 2), "Медиана (д.)": round(med_v, 2), "P85 (д.)": round(p85_v, 2),
                    "Задач с этапом": cnt_v
                })
            stat_table_df = pd.DataFrame(status_stats)
            st.dataframe(stat_table_df, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader("Сравнение времени этапов по задачам")
            fig_phases = go.Figure()
            fig_phases.add_trace(go.Bar(name="Аналитика (Очередь/Ревью)", x=summary_df["Задача"], y=summary_df.get("Очередь/Ревью Аналитики (д.)", 0), marker_color="#ffbb78"))
            fig_phases.add_trace(go.Bar(name="Аналитика (Работа)", x=summary_df["Задача"], y=summary_df.get("В аналитике (д.)", 0), marker_color="#aec7e8"))
            fig_phases.add_trace(go.Bar(name="Разработка (Очередь/Ревью)", x=summary_df["Задача"], y=summary_df.get("Очередь/Код Ревью Dev (д.)", 0), marker_color="#ff7f0e"))
            fig_phases.add_trace(go.Bar(name="Разработка (Работа)", x=summary_df["Задача"], y=summary_df.get("В разработке (д.)", 0), marker_color="#1f77b4"))
            fig_phases.add_trace(go.Bar(name="QA (Очередь/Доработки)", x=summary_df["Задача"], y=summary_df.get("Очередь ожидания QA (дни)", 0) + summary_df.get("Доработки у dev (дни)", 0), marker_color="#d62728"))
            fig_phases.add_trace(go.Bar(name="QA (Тестирование)", x=summary_df["Задача"], y=summary_df.get("В тестировании (дни)", 0), marker_color="#2ca02c"))
            fig_phases.update_layout(barmode="stack", xaxis_title="Задача", yaxis_title="Рабочие дни (д.)", height=380)
            st.plotly_chart(fig_phases, use_container_width=True)

        # ==================================================================
        # 2. СРАВНЕНИЕ ПЕРИОДОВ (СПРИНТЫ / КВАРТАЛЫ)
        # ==================================================================
        with tab_sprints_cmp:
            st.subheader("📅 Сравнительный анализ периодов поставки")
            st.caption("Динамика сквозной воронки поставки и ключевых метрик по каждой роли")

            compare_scale = st.radio(
                "Масштаб сравнения:",
                options=["По месячным спринтам", "По кварталам"],
                horizontal=True
            )

            active_compare_list = monthly_sprints_list if compare_scale == "По месячным спринтам" else quarter_list

            compare_rows = []
            for p_item in active_compare_list:
                sp_sub = full_raw_df[
                    (full_raw_df["timestamp"].dt.date >= p_item["start_date"])
                    & (full_raw_df["timestamp"].dt.date <= p_item["end_date"])
                    & (full_raw_df["changed_value"] == "Текущий статус")
                ]
                sp_task_ids = sp_sub["task_identifier"].dropna().unique()
                sp_df = global_summary_df[global_summary_df["Задача"].isin(sp_task_ids)]

                if not sp_df.empty:
                    lt_m, lt_med, lt_p85, _ = calc_stats(sp_df["Полный Lead Time (д.)"])
                    wt_m, wt_med, wt_p85, _ = calc_stats(sp_df["Всего очередей (д.)"])
                    wk_m, wk_med, wk_p85, _ = calc_stats(sp_df["Чистая работа (д.)"])
                    fl_m, fl_med, _, _ = calc_stats(sp_df["Сквозной Flow Efficiency (%)"])

                    qa_act = sp_df[sp_df["В тестировании (дни)"] > 0]
                    qa_w_m, qa_w_med, qa_w_p85, _ = calc_stats(qa_act["В тестировании (дни)"])
                    qa_q_m, qa_q_med, qa_q_p85, _ = calc_stats(qa_act["Очередь ожидания QA (дни)"])
                    qa_c_m, qa_c_med, qa_c_p85, _ = calc_stats(qa_act["Циклтайм QA (дни)"])
                    qa_fl_m, _, _, _ = calc_stats(qa_act["Flow Efficiency QA (%)"])

                    dev_act = sp_df[sp_df["В разработке (д.)"] > 0]
                    dev_w_m, dev_w_med, dev_w_p85, _ = calc_stats(dev_act["В разработке (д.)"])
                    dev_q_m, dev_q_med, dev_q_p85, _ = calc_stats(dev_act["Очередь/Код Ревью Dev (д.)"])
                    dev_c_m, dev_c_med, dev_c_p85, _ = calc_stats(dev_act["Цикл Разработки (д.)"])
                    dev_fl_m, _, _, _ = calc_stats(dev_act["Flow Разработки (%)"])

                    an_act = sp_df[sp_df["В аналитике (д.)"] > 0]
                    an_w_m, an_w_med, an_w_p85, _ = calc_stats(an_act["В аналитике (д.)"])
                    an_q_m, an_q_med, an_q_p85, _ = calc_stats(an_act["Очередь/Ревью Аналитики (д.)"])
                    an_c_m, an_c_med, an_c_p85, _ = calc_stats(an_act["Цикл Аналитики (д.)"])
                    an_fl_m, _, _, _ = calc_stats(an_act["Flow Аналитики (%)"])

                    compare_rows.append({
                        "Период": p_item["period_name"],
                        "Задач (шт)": len(sp_task_ids),
                        "Lead Time Ср (д.)": round(lt_m, 2),
                        "Lead Time Мед (д.)": round(lt_med, 2),
                        "Lead Time P85 (д.)": round(lt_p85, 2),
                        "Очереди Ср (д.)": round(wt_m, 2),
                        "Чистая работа Ср (д.)": round(wk_m, 2),
                        "Сквозной Flow (%)": round(fl_m, 1),
                        "QA В тестировании Ср (д.)": round(qa_w_m, 2),
                        "QA Очередь Ср (д.)": round(qa_q_m, 2),
                        "QA Циклтайм Ср (д.)": round(qa_c_m, 2),
                        "QA Flow (%)": round(qa_fl_m, 1),
                        "Dev В разработке Ср (д.)": round(dev_w_m, 2),
                        "Dev Очередь/Ревью Ср (д.)": round(dev_q_m, 2),
                        "Dev Цикл Ср (д.)": round(dev_c_m, 2),
                        "Dev Flow (%)": round(dev_fl_m, 1),
                        "An В аналитике Ср (д.)": round(an_w_m, 2),
                        "An Очередь/Ревью Ср (д.)": round(an_q_m, 2),
                        "An Цикл Ср (д.)": round(an_c_m, 2),
                        "An Flow (%)": round(an_fl_m, 1),
                    })

            cmp_df = pd.DataFrame(compare_rows)

            if not cmp_df.empty:
                st.markdown("#### 1. Сквозная воронка поставки по периодам")
                overview_cols = [
                    "Период", "Задач (шт)",
                    "Lead Time Ср (д.)", "Lead Time Мед (д.)", "Lead Time P85 (д.)",
                    "Очереди Ср (д.)", "Чистая работа Ср (д.)", "Сквозной Flow (%)"
                ]
                st.dataframe(cmp_df[overview_cols], use_container_width=True, hide_index=True)

                c_g1, c_g2 = st.columns(2)
                with c_g1:
                    fig_lt = px.bar(
                        cmp_df,
                        x="Период",
                        y=["Lead Time Ср (д.)", "Lead Time Мед (д.)", "Lead Time P85 (д.)"],
                        barmode="group",
                        title="Сквозной Lead Time (Среднее / Медиана / P85)",
                        text_auto=".2f",
                        color_discrete_sequence=["#1f77b4", "#aec7e8", "#ff7f0e"]
                    )
                    fig_lt.update_layout(height=360, yaxis_title="Рабочие дни (д.)")
                    st.plotly_chart(fig_lt, use_container_width=True)

                with c_g2:
                    fig_work_wait = px.bar(
                        cmp_df,
                        x="Период",
                        y=["Чистая работа Ср (д.)", "Очереди Ср (д.)"],
                        barmode="group",
                        title="Соотношение чистой работы и очередей (д.)",
                        text_auto=".2f",
                        color_discrete_sequence=["#2ca02c", "#d62728"]
                    )
                    fig_work_wait.update_layout(height=360, yaxis_title="Рабочие дни (д.)")
                    st.plotly_chart(fig_work_wait, use_container_width=True)

                st.markdown("---")
                st.markdown("#### 2. Сравнение метрик и Flow по ролям")

                role_tab_qa, role_tab_dev, role_tab_an = st.tabs([
                    "🧪 Тестирование (QA)",
                    "💻 Разработка (Dev)",
                    "📐 Аналитика (Analytics)",
                ])

                with role_tab_qa:
                    qa_cmp_cols = ["Период", "QA В тестировании Ср (д.)", "QA Очередь Ср (д.)", "QA Циклтайм Ср (д.)", "QA Flow (%)"]
                    st.dataframe(cmp_df[qa_cmp_cols], use_container_width=True, hide_index=True)

                    fig_qa_cmp = px.bar(
                        cmp_df,
                        x="Период",
                        y=["QA В тестировании Ср (д.)", "QA Очередь Ср (д.)", "QA Циклтайм Ср (д.)"],
                        barmode="group",
                        title="Динамика этапа QA (в днях)",
                        text_auto=".2f",
                        color_discrete_sequence=["#2ca02c", "#d62728", "#1f77b4"]
                    )
                    fig_qa_cmp.update_layout(height=350, yaxis_title="Рабочие дни (д.)")
                    st.plotly_chart(fig_qa_cmp, use_container_width=True)

                with role_tab_dev:
                    dev_cmp_cols = ["Период", "Dev В разработке Ср (д.)", "Dev Очередь/Ревью Ср (д.)", "Dev Цикл Ср (д.)", "Dev Flow (%)"]
                    st.dataframe(cmp_df[dev_cmp_cols], use_container_width=True, hide_index=True)

                    fig_dev_cmp = px.bar(
                        cmp_df,
                        x="Период",
                        y=["Dev В разработке Ср (д.)", "Dev Очередь/Ревью Ср (д.)", "Dev Цикл Ср (д.)"],
                        barmode="group",
                        title="Динамика этапа разработки (в днях)",
                        text_auto=".2f",
                        color_discrete_sequence=["#1f77b4", "#ff7f0e", "#9467bd"]
                    )
                    fig_dev_cmp.update_layout(height=350, yaxis_title="Рабочие дни (д.)")
                    st.plotly_chart(fig_dev_cmp, use_container_width=True)

                with role_tab_an:
                    an_cmp_cols = ["Период", "An В аналитике Ср (д.)", "An Очередь/Ревью Ср (д.)", "An Цикл Ср (д.)", "An Flow (%)"]
                    st.dataframe(cmp_df[an_cmp_cols], use_container_width=True, hide_index=True)

                    fig_an_cmp = px.bar(
                        cmp_df,
                        x="Период",
                        y=["An В аналитике Ср (д.)", "An Очередь/Ревью Ср (д.)", "An Цикл Ср (д.)"],
                        barmode="group",
                        title="Динамика этапа аналитики (в днях)",
                        text_auto=".2f",
                        color_discrete_sequence=["#aec7e8", "#ffbb78", "#2ca02c"]
                    )
                    fig_an_cmp.update_layout(height=350, yaxis_title="Рабочие дни (д.)")
                    st.plotly_chart(fig_an_cmp, use_container_width=True)
            else:
                st.info("Недостаточно данных для построения сравнительного анализа.")

        # ==================================================================
        # 3. ОЦЕНКА ЗАДАЧ (ESTIMATION)
        # ==================================================================
        with tab_estimates:
            st.subheader("🎯 Анализ точности и калибровка оценок задач (T-Shirt Sizes)")
            st.caption("Сопоставление плановых и фактических размеров (XS, S, M, L, XL) и калибровка фактическими рабочими днями")

            est_df = summary_df.copy()

            def eval_accuracy(plan_col, fact_col, data):
                valid = data[(data[plan_col].isin(TSHIRT_ORDER)) & (data[fact_col].isin(TSHIRT_ORDER))]
                if valid.empty:
                    return 0, 0, 0, 0
                total = len(valid)
                order_map = {k: i for i, k in enumerate(TSHIRT_ORDER)}
                exact = (valid[plan_col] == valid[fact_col]).sum()
                under = (valid[fact_col].map(order_map) > valid[plan_col].map(order_map)).sum()
                over = (valid[fact_col].map(order_map) < valid[plan_col].map(order_map)).sum()
                return total, (exact / total * 100), (under / total * 100), (over / total * 100)

            tot_d, acc_d, under_d, over_d = eval_accuracy("dev_plan", "dev_fact", est_df)
            tot_q, acc_q, under_q, over_q = eval_accuracy("qa_plan", "qa_fact", est_df)
            tot_a, acc_a, under_a, over_a = eval_accuracy("an_plan", "an_fact", est_df)

            e1, e2, e3, e4 = st.columns(4)
            avg_acc = (acc_d + acc_q + acc_a) / 3 if (tot_d or tot_q or tot_a) else 0.0
            avg_under = (under_d + under_q + under_a) / 3 if (tot_d or tot_q or tot_a) else 0.0

            e1.metric("Точность эстимации (План=Факт)", f"{avg_acc:.1f}%")
            e2.metric("Недооценка сложности (Факт > План)", f"{avg_under:.1f}%", delta_color="inverse")
            e3.metric("Задач с оценкой разработки", f"{tot_d} шт")
            e4.metric("Задач с оценкой QA", f"{tot_q} шт")

            st.markdown("---")
            st.markdown("#### 1. Калибровка T-Shirt размеров фактическими днями")

            est_role_qa, est_role_dev, est_role_an = st.tabs([
                "🧪 Тестирование (QA)",
                "💻 Разработка (Dev)",
                "📐 Аналитика (Analytics)",
            ])

            def render_calibration(role_name, plan_col, fact_col, days_col, data):
                col_tbl, col_chart = st.columns([1, 1])
                cal_rows = []
                for sz in TSHIRT_ORDER:
                    sub = data[data[fact_col] == sz]
                    cnt = len(sub)
                    if cnt > 0:
                        mean_d, med_d, p85_d, _ = calc_stats(sub[days_col])
                    else:
                        mean_d = med_d = p85_d = 0.0
                    cal_rows.append({
                        "Размер": sz,
                        "Задач (шт)": cnt,
                        "Среднее (д.)": round(mean_d, 2),
                        "Медиана (д.)": round(med_d, 2),
                        "P85 SLE (д.)": round(p85_d, 2),
                    })
                cal_df = pd.DataFrame(cal_rows)
                with col_tbl:
                    st.markdown(f"**Эталонные ориентиры {role_name} (по фактическому размеру):**")
                    st.dataframe(cal_df, use_container_width=True, hide_index=True)

                with col_chart:
                    valid_counts = []
                    for sz in TSHIRT_ORDER:
                        p_cnt = (data[plan_col] == sz).sum()
                        f_cnt = (data[fact_col] == sz).sum()
                        valid_counts.append({"Размер": sz, "Тип": "План", "Количество": p_cnt})
                        valid_counts.append({"Размер": sz, "Тип": "Факт", "Количество": f_cnt})
                    fig_pf = px.bar(
                        pd.DataFrame(valid_counts),
                        x="Размер",
                        y="Количество",
                        color="Тип",
                        barmode="group",
                        title=f"Распределение {role_name}: План vs Факт",
                        color_discrete_map={"План": "#1f77b4", "Факт": "#2ca02c"}
                    )
                    fig_pf.update_layout(height=300)
                    st.plotly_chart(fig_pf, use_container_width=True)

            with est_role_qa:
                render_calibration("QA", "qa_plan", "qa_fact", "В тестировании (дни)", est_df)

            with est_role_dev:
                render_calibration("Разработки", "dev_plan", "dev_fact", "В разработке (д.)", est_df)

            with est_role_an:
                render_calibration("Аналитики", "an_plan", "an_fact", "В аналитике (д.)", est_df)

            st.markdown("---")
            st.markdown("#### 2. Реестр оценок по задачам")

            filter_mismatch = st.checkbox("Показать только задачи с несовпадением Плана и Факта", value=False)

            tbl_est = est_df[[
                "Задача", "task_size",
                "an_plan", "an_fact", "В аналитике (д.)",
                "dev_plan", "dev_fact", "В разработке (д.)",
                "qa_plan", "qa_fact", "В тестировании (дни)",
                "Полный Lead Time (д.)"
            ]].copy()

            tbl_est = tbl_est.rename(columns={
                "task_size": "Размер задачи",
                "an_plan": "План Аналитика", "an_fact": "Факт Аналитика", "В аналитике (д.)": "Дней в аналитике",
                "dev_plan": "План Dev", "dev_fact": "Факт Dev", "В разработке (д.)": "Дней в dev",
                "qa_plan": "План QA", "qa_fact": "Факт QA", "В тестировании (дни)": "Дней в QA"
            })

            if filter_mismatch:
                tbl_est = tbl_est[
                    (tbl_est["План Dev"] != tbl_est["Факт Dev"])
                    | (tbl_est["План QA"] != tbl_est["Факт QA"])
                    | (tbl_est["План Аналитика"] != tbl_est["Факт Аналитика"])
                ]

            search_est_q = st.text_input("🔍 Быстрый поиск задачи по номеру:", placeholder="Например: 2421", key="search_est_table")
            if search_est_q.strip():
                tbl_est = tbl_est[tbl_est["Задача"].astype(str).str.contains(search_est_q.strip(), case=False, na=False)]

            st.caption(f"Отображено задач: **{len(tbl_est)}** из **{len(est_df)}**")
            st.dataframe(tbl_est, use_container_width=True, hide_index=True)

            csv_est_exp = tbl_est.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 Скачать реестр оценок (CSV)", csv_est_exp, "task_estimations.csv", "text/csv")

        # ==================================================================
        # 4. КОНТРОЛЬ ДЕДЛАЙНОВ (SLA)
        # ==================================================================
        with tab_deadlines:
            st.subheader("⏰ Контроль выполнения обязательств и дедлайнов (SLA)")
            st.caption("Анализ соблюдения сроков заказчика, частоты переносов дедлайнов (Slippage) и просрочек")

            deadlines_df = summary_df[summary_df["has_deadline"] == True].copy()

            if not deadlines_df.empty:
                total_with_dl = len(deadlines_df)
                on_time_tasks = deadlines_df[deadlines_df["sla_status"] == "В срок (On-Time)"]
                overdue_tasks = deadlines_df[deadlines_df["sla_status"].isin(["С опозданием (Overdue)", "В работе (просрочено)"])]
                shifted_tasks = deadlines_df[deadlines_df["deadline_shifts"] > 0]

                on_time_pct = (len(on_time_tasks) / total_with_dl * 100) if total_with_dl > 0 else 0.0
                overdue_pct = (len(overdue_tasks) / total_with_dl * 100) if total_with_dl > 0 else 0.0
                shifted_pct = (len(shifted_tasks) / total_with_dl * 100) if total_with_dl > 0 else 0.0

                avg_slippage = shifted_tasks["deadline_slippage_days"].mean() if not shifted_tasks.empty else 0.0
                max_slippage = shifted_tasks["deadline_slippage_days"].max() if not shifted_tasks.empty else 0.0

                dl1, dl2, dl3, dl4 = st.columns(4)
                dl1.metric("Сдано в срок (On-Time Rate)", f"{on_time_pct:.1f}%", f"{len(on_time_tasks)} из {total_with_dl} задач")
                dl2.metric("Просрочено (Overdue)", f"{overdue_pct:.1f}%", f"{len(overdue_tasks)} задач", delta_color="inverse")
                dl3.metric("Задач с переносом срока", f"{shifted_pct:.1f}%", f"{len(shifted_tasks)} тикетов", delta_color="inverse")
                dl4.metric("Средний сдвиг дедлайна", f"{avg_slippage:.1f} д.", f"Макс: {max_slippage} д.")

                st.markdown("---")
                c_dl_pie, c_dl_bar = st.columns(2)

                with c_dl_pie:
                    fig_sla_pie = px.pie(
                        deadlines_df,
                        names="sla_status",
                        title="Распределение задач по статусу дедлайна",
                        hole=0.45,
                        color="sla_status",
                        color_discrete_map={
                            "В срок (On-Time)": "#2ca02c",
                            "В работе (в графике)": "#1f77b4",
                            "С опозданием (Overdue)": "#d62728",
                            "В работе (просрочено)": "#ff7f0e",
                        }
                    )
                    fig_sla_pie.update_layout(height=340)
                    st.plotly_chart(fig_sla_pie, use_container_width=True)

                with c_dl_bar:
                    if not shifted_tasks.empty:
                        fig_slip_hist = px.histogram(
                            shifted_tasks,
                            x="deadline_slippage_days",
                            nbins=15,
                            title="Распределение величины переноса дедлайнов (в днях)",
                            color_discrete_sequence=["#ff7f0e"]
                        )
                        fig_slip_hist.update_layout(height=340, xaxis_title="Сдвиг дедлайна (календарных дней)", yaxis_title="Количество задач")
                        st.plotly_chart(fig_slip_hist, use_container_width=True)
                    else:
                        st.info("В выборке нет задач с переносами дедлайнов.")

                st.markdown("---")
                st.markdown("#### 📋 Реестр задач с дедлайнами заказчика")

                col_flt_sla, col_srch_dl = st.columns([1, 1])
                with col_flt_sla:
                    sla_filter_opts = st.multiselect(
                        "Фильтр по статусу SLA:",
                        options=deadlines_df["sla_status"].unique(),
                        default=deadlines_df["sla_status"].unique()
                    )
                with col_srch_dl:
                    srch_dl_q = st.text_input("🔍 Поиск задачи по номеру:", placeholder="Например: 2421", key="search_dl_tbl")

                display_dl_df = deadlines_df.copy()
                if sla_filter_opts:
                    display_dl_df = display_dl_df[display_dl_df["sla_status"].isin(sla_filter_opts)]
                if srch_dl_q.strip():
                    display_dl_df = display_dl_df[display_dl_df["Задача"].astype(str).str.contains(srch_dl_q.strip(), case=False, na=False)]

                display_dl_df["Первый дедлайн"] = display_dl_df["first_deadline"].dt.strftime("%d.%m.%Y")
                display_dl_df["Финальный дедлайн"] = display_dl_df["final_deadline"].dt.strftime("%d.%m.%Y")
                display_dl_df["Дата завершения"] = display_dl_df["finished_at"].apply(lambda d: d.strftime("%d.%m.%Y %H:%M") if pd.notna(d) else "В процессе")

                display_dl_df = display_dl_df.rename(columns={
                    "task_size": "Размер",
                    "deadline_shifts": "Переносов (раз)",
                    "deadline_slippage_days": "Сдвиг (дней)",
                    "sla_status": "Статус SLA",
                    "delay_days": "Отклонение (дней)"
                })

                rename_dl_cols = [
                    "Задача", "Размер", "Первый дедлайн", "Финальный дедлайн",
                    "Переносов (раз)", "Сдвиг (дней)", "Дата завершения",
                    "Статус SLA", "Отклонение (дней)", "Полный Lead Time (д.)"
                ]

                st.caption(f"Отображено: **{len(display_dl_df)}** из **{total_with_dl}** задач с установленным дедлайном")
                st.dataframe(display_dl_df[rename_dl_cols], use_container_width=True, hide_index=True)

                csv_dl_exp = display_dl_df[rename_dl_cols].to_csv(index=False).encode("utf-8-sig")
                st.download_button("📥 Скачать реестр дедлайнов (CSV)", csv_dl_exp, "task_deadlines_sla.csv", "text/csv")
            else:
                st.info("В выбранном периоде нет задач с заполненным полем «Дедлайн заказчика».")

        # ==================================================================
        # 5. ДЕФЕКТЫ VS ФИЧИ (TYPE)
        # ==================================================================
        with tab_types:
            st.subheader("🐞 Анализ структуры потока: Дефекты (Bugs) vs Фичи / Задачи (Tasks)")
            st.caption("Оценка баланса создания новой ценности (Value Demand) и устранения дефектов (Failure Demand)")

            types_df = summary_df.copy()

            bugs_df = types_df[types_df["Тип задачи"] == "Дефект (Bug)"]
            features_df = types_df[types_df["Тип задачи"].isin(["Фича / Задача (Task)", "Эпик (Epic)"])]

            total_cnt = len(types_df)
            bug_cnt = len(bugs_df)
            feat_cnt = len(features_df)

            bug_pct = (bug_cnt / total_cnt * 100) if total_cnt > 0 else 0.0
            feat_pct = (feat_cnt / total_cnt * 100) if total_cnt > 0 else 0.0

            bug_lt_m, bug_lt_med, bug_lt_p85, _ = calc_stats(bugs_df.get("Полный Lead Time (д.)", pd.Series(dtype=float)))
            feat_lt_m, feat_lt_med, feat_lt_p85, _ = calc_stats(features_df.get("Полный Lead Time (д.)", pd.Series(dtype=float)))

            t_c1, t_c2, t_c3, t_c4 = st.columns(4)
            t_c1.metric("Доля дефектов (Failure Demand)", f"{bug_pct:.1f}%", f"{bug_cnt} багов", delta_color="inverse")
            t_c2.metric("Доля фичей (Value Demand)", f"{feat_pct:.1f}%", f"{feat_cnt} задач/эпиков")
            t_c3.metric("Lead Time Дефектов (Ср / P85)", f"{bug_lt_m:.1f} д.", f"P85: {bug_lt_p85:.1f} д.")
            t_c4.metric("Lead Time Фичей (Ср / P85)", f"{feat_lt_m:.1f} д.", f"P85: {feat_lt_p85:.1f} д.")

            st.markdown("---")
            t_col_g1, t_col_g2 = st.columns(2)

            with t_col_g1:
                fig_type_pie = px.pie(
                    types_df,
                    names="Тип задачи",
                    title="Структура потока задач в периоде (Flow Distribution)",
                    hole=0.45,
                    color="Тип задачи",
                    color_discrete_map={
                        "Дефект (Bug)": "#d62728",
                        "Фича / Задача (Task)": "#1f77b4",
                        "Эпик (Epic)": "#9467bd",
                        "Эксплуатация (Run)": "#ff7f0e",
                        "Техдолг": "#7f7f7f",
                        "Не определен": "#c7c7c7",
                    }
                )
                fig_type_pie.update_layout(height=340)
                st.plotly_chart(fig_type_pie, use_container_width=True)

            with t_col_g2:
                compare_phases_data = []
                for group_name, g_df in [("Дефекты (Bugs)", bugs_df), ("Фичи (Tasks/Epics)", features_df)]:
                    if not g_df.empty:
                        compare_phases_data.append({
                            "Категория": group_name,
                            "В аналитике (д.)": g_df["В аналитике (д.)"].mean(),
                            "В разработке (д.)": g_df["В разработке (д.)"].mean(),
                            "В тестировании (дни)": g_df["В тестировании (дни)"].mean(),
                            "Очереди и ревью (д.)": g_df["Всего очередей (д.)"].mean(),
                        })
                if compare_phases_data:
                    fig_comp_bar = px.bar(
                        pd.DataFrame(compare_phases_data),
                        x="Категория",
                        y=["В аналитике (д.)", "В разработке (д.)", "В тестировании (дни)", "Очереди и ревью (д.)"],
                        barmode="group",
                        title="Среднее время фаз: Баги vs Фичи (в днях)",
                        text_auto=".2f",
                        color_discrete_sequence=["#aec7e8", "#1f77b4", "#2ca02c", "#d62728"]
                    )
                    fig_comp_bar.update_layout(height=340, yaxis_title="Рабочие дни (д.)")
                    st.plotly_chart(fig_comp_bar, use_container_width=True)

            st.markdown("---")
            st.markdown("#### 📋 Сводная таблица по типам задач")

            col_t_flt, col_t_srch = st.columns([1, 1])
            with col_t_flt:
                sel_types_filter = st.multiselect(
                    "Фильтр по типу задачи:",
                    options=types_df["Тип задачи"].unique(),
                    default=types_df["Тип задачи"].unique()
                )
            with col_t_srch:
                search_type_q = st.text_input("🔍 Быстрый поиск задачи по номеру:", placeholder="Например: 2421", key="search_type_tbl")

            filtered_types_df = types_df.copy()
            if sel_types_filter:
                filtered_types_df = filtered_types_df[filtered_types_df["Тип задачи"].isin(sel_types_filter)]
            if search_type_q.strip():
                filtered_types_df = filtered_types_df[filtered_types_df["Задача"].astype(str).str.contains(search_type_q.strip(), case=False, na=False)]

            tbl_type_cols = [
                "Задача", "Тип задачи", "task_size",
                "В аналитике (д.)", "В разработке (д.)", "В тестировании (дни)",
                "Всего очередей (д.)", "Полный Lead Time (д.)", "Сквозной Flow Efficiency (%)"
            ]

            st.caption(f"Отображено задач: **{len(filtered_types_df)}** из **{total_cnt}**")
            st.dataframe(filtered_types_df[tbl_type_cols], use_container_width=True, hide_index=True)

            csv_types_exp = filtered_types_df[tbl_type_cols].to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 Скачать реестр по типам задач (CSV)", csv_types_exp, "tasks_by_type.csv", "text/csv")

        # ==================================================================
        # 6. ПРИОРИТЕТЫ И ОЧЕРЕДИ (QUEUE DISCIPLINE)
        # ==================================================================
        with tab_priorities:
            st.subheader("⚡ Влияние приоритета на прохождение очереди и Lead Time")
            st.caption("Проверка дисциплины очередей: насколько быстрее берутся в работу высокоприоритетные задачи")

            prio_df = summary_df.copy()

            prio_stat_rows = []
            for pr in PRIORITY_ORDER:
                sub_p = prio_df[prio_df["Приоритет"] == pr]
                cnt = len(sub_p)
                if cnt > 0:
                    mean_lt, med_lt, p85_lt, _ = calc_stats(sub_p.get("Полный Lead Time (д.)", pd.Series(dtype=float)))
                    mean_wt, med_wt, p85_wt, _ = calc_stats(sub_p.get("Всего очередей (д.)", pd.Series(dtype=float)))
                    mean_qa_q, _, _, _ = calc_stats(sub_p.get("Очередь ожидания QA (дни)", pd.Series(dtype=float)))
                    mean_dev_q, _, _, _ = calc_stats(sub_p.get("К разработке (д.)", pd.Series(dtype=float)))
                    mean_flow, _, _, _ = calc_stats(sub_p.get("Сквозной Flow Efficiency (%)", pd.Series(dtype=float)))
                else:
                    mean_lt = med_lt = p85_lt = 0.0
                    mean_wt = med_wt = p85_wt = 0.0
                    mean_qa_q = mean_dev_q = mean_flow = 0.0

                prio_stat_rows.append({
                    "Приоритет": pr,
                    "Задач (шт)": cnt,
                    "Lead Time Ср (д.)": round(mean_lt, 2),
                    "Lead Time P85 (д.)": round(p85_lt, 2),
                    "Всего очередей Ср (д.)": round(mean_wt, 2),
                    "Очередь Dev Ср (д.)": round(mean_dev_q, 2),
                    "Очередь QA Ср (д.)": round(mean_qa_q, 2),
                    "Flow Efficiency (%)": round(mean_flow, 1),
                })

            prio_stat_table = pd.DataFrame(prio_stat_rows)
            st.markdown("#### 1. Сводная статистика очередей по приоритетам")
            st.dataframe(prio_stat_table, use_container_width=True, hide_index=True)

            st.markdown("---")
            p_col1, p_col2 = st.columns(2)

            with p_col1:
                active_prio_stats = prio_stat_table[prio_stat_table["Задач (шт)"] > 0]
                fig_prio_wait = px.bar(
                    active_prio_stats,
                    x="Приоритет",
                    y=["Всего очередей Ср (д.)", "Lead Time Ср (д.)"],
                    barmode="group",
                    title="Сравнение очередей и Lead Time по уровням приоритета (д.)",
                    text_auto=".2f",
                    color_discrete_sequence=["#d62728", "#1f77b4"]
                )
                fig_prio_wait.update_layout(height=350, yaxis_title="Рабочие дни (д.)")
                st.plotly_chart(fig_prio_wait, use_container_width=True)

            with p_col2:
                fig_prio_flow = px.bar(
                    active_prio_stats,
                    x="Приоритет",
                    y="Flow Efficiency (%)",
                    title="Flow Efficiency по приоритетам (доля полезного времени)",
                    text_auto=".1f",
                    color_discrete_sequence=["#2ca02c"]
                )
                fig_prio_flow.update_layout(height=350, yaxis_title="% полезной работы")
                st.plotly_chart(fig_prio_flow, use_container_width=True)

            st.markdown("---")
            st.markdown("#### 2. Реестр задач с анализом очередей по приоритетам")

            c_pflt1, c_pflt2 = st.columns([1, 1])
            with c_pflt1:
                sel_prio_filter = st.multiselect(
                    "Фильтр по приоритету:",
                    options=prio_df["Приоритет"].unique(),
                    default=prio_df["Приоритет"].unique()
                )
            with c_pflt2:
                search_prio_q = st.text_input("🔍 Быстрый поиск задачи по номеру:", placeholder="Например: 2421", key="search_prio_tbl")

            filtered_prio_df = prio_df.copy()
            if sel_prio_filter:
                filtered_prio_df = filtered_prio_df[filtered_prio_df["Приоритет"].isin(sel_prio_filter)]
            if search_prio_q.strip():
                filtered_prio_df = filtered_prio_df[filtered_prio_df["Задача"].astype(str).str.contains(search_prio_q.strip(), case=False, na=False)]

            tbl_prio_cols = [
                "Задача", "Приоритет", "Ранг в очереди", "Тип задачи",
                "К разработке (д.)", "Очередь ожидания QA (дни)", "Всего очередей (д.)",
                "Чистая работа (д.)", "Полный Lead Time (д.)", "Сквозной Flow Efficiency (%)"
            ]

            st.caption(f"Отображено: **{len(filtered_prio_df)}** из **{len(prio_df)}** задач")
            st.dataframe(filtered_prio_df[tbl_prio_cols], use_container_width=True, hide_index=True)

            csv_prio_exp = filtered_prio_df[tbl_prio_cols].to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 Скачать реестр очередей по приоритетам (CSV)", csv_prio_exp, "tasks_by_priority.csv", "text/csv")

        # ==================================================================
        # 7. АУДИТ ТЕСТИРОВАНИЯ QA
        # ==================================================================
        with tab_qa:
            st.subheader("🧪 Комплексный аудит направления QA")
            q_sub1, q_sub2, q_sub3, q_sub4 = st.tabs([
                "📊 Метрики и Flow QA",
                "👥 Аналитика по тестировщикам",
                "🔧 Доработки у разработчиков",
                "📋 Журнал итераций QA",
            ])

            with q_sub1:
                qa_stat_df = summary_df[summary_df["В тестировании (дни)"] > 0].copy() if only_qa_active else summary_df.copy()
                avg_w, med_w, p85_w, _ = calc_stats(qa_stat_df.get("В тестировании (дни)", pd.Series(dtype=float)))
                avg_q, med_q, p85_q, _ = calc_stats(qa_stat_df.get("Очередь ожидания QA (дни)", pd.Series(dtype=float)))
                avg_c, med_c, p85_c, _ = calc_stats(qa_stat_df.get("Циклтайм QA (дни)", pd.Series(dtype=float)))
                avg_f, med_f, p85_f, _ = calc_stats(qa_stat_df.get("Flow Efficiency QA (%)", pd.Series(dtype=float)))

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("В тестировании", f"{avg_w:.2f} д.", f"Мед: {med_w:.2f} | P85: {p85_w:.2f}")
                c2.metric("Очередь QA", f"{avg_q:.2f} д.", f"Мед: {med_q:.2f} | P85: {p85_q:.2f}", delta_color="inverse")
                c3.metric("Циклтайм QA", f"{avg_c:.2f} д.", f"Мед: {med_c:.2f} | P85: {p85_c:.2f}")
                c4.metric("Flow QA", f"{avg_f:.1f}%", f"Мед: {med_f:.1f}% | P85: {p85_f:.1f}%")

                st.markdown("---")
                st.markdown("##### Сводная таблица по задачам (в днях)")
                qa_display_cols = [
                    "Задача",
                    "В тестировании (дни)",
                    "Очередь ожидания QA (дни)",
                    "Циклтайм QA (дни)",
                    "Доработки у dev (дни)",
                    "Итераций QA",
                    "Flow Efficiency QA (%)",
                ]

                qa_metrics_only = [col for col in qa_display_cols if col != "Задача"]
                qa_table_filtered = summary_df[qa_display_cols][
                    (summary_df[qa_metrics_only] > 0).any(axis=1)
                ]

                if not qa_table_filtered.empty:
                    st.dataframe(qa_table_filtered, use_container_width=True, hide_index=True)
                else:
                    st.info("В выбранном периоде нет задач с активностью на этапе QA.")

            with q_sub2:
                if not qa_iter_df.empty:
                    qa_grouped = qa_iter_df.groupby(["Исполнитель", "Роль"]).agg(
                        tasks=("Задача", "nunique"), iters=("Итерация", "count"), days=("Раб. дней", "sum")
                    ).reset_index()
                    qa_grouped["avg_per_task"] = (qa_grouped["days"] / qa_grouped["tasks"]).round(2)
                    qa_grouped = qa_grouped.rename(columns={"tasks": "Задач (шт)", "iters": "Проверок (шт)", "days": "Суммарно (д.)", "avg_per_task": "Среднее на задачу (д.)"})
                    st.dataframe(qa_grouped, use_container_width=True, hide_index=True)
                else:
                    st.info("Нет данных по исполнителям QA.")

            with q_sub3:
                st.markdown("##### 🔧 Возвраты из QA на доработку разработчикам")
                if not reworks_df.empty:
                    st.dataframe(reworks_df, use_container_width=True, hide_index=True)
                else:
                    st.success("В этом периоде нет возвратов из QA.")

            with q_sub4:
                render_searchable_log(qa_iter_df, "Задача", "Журнал подходов к тестированию", "qa_iterations.csv", "qa_log")

        # ==================================================================
        # 8. АУДИТ РАЗРАБОТКИ
        # ==================================================================
        with tab_dev:
            st.subheader("💻 Комплексный аудит разработки")
            dev_sub1, dev_sub2, dev_sub3, dev_sub4 = st.tabs([
                "📊 Метрики и Flow Dev",
                "👥 Аналитика по разработчикам",
                "🔍 Анализ Код Ревью",
                "📋 Журнал итераций Dev",
            ])

            with dev_sub1:
                dev_stat_df = summary_df[summary_df["В разработке (д.)"] > 0].copy() if only_qa_active else summary_df.copy()
                dw_m, dw_med, dw_p85, _ = calc_stats(dev_stat_df.get("В разработке (д.)", pd.Series(dtype=float)))
                dq_m, dq_med, dq_p85, _ = calc_stats(dev_stat_df.get("Очередь/Код Ревью Dev (д.)", pd.Series(dtype=float)))
                dc_m, dc_med, dc_p85, _ = calc_stats(dev_stat_df.get("Цикл Разработки (д.)", pd.Series(dtype=float)))
                df_m, df_med, df_p85, _ = calc_stats(dev_stat_df.get("Flow Разработки (%)", pd.Series(dtype=float)))

                d1, d2, d3, d4 = st.columns(4)
                d1.metric("В разработке", f"{dw_m:.2f} д.", f"Мед: {dw_med:.2f} | P85: {dw_p85:.2f}")
                d2.metric("Очередь + Код Ревью", f"{dq_m:.2f} д.", f"Мед: {dq_med:.2f} | P85: {dq_p85:.2f}", delta_color="inverse")
                d3.metric("Цикл Разработки", f"{dc_m:.2f} д.", f"Мед: {dc_med:.2f} | P85: {dc_p85:.2f}")
                d4.metric("Flow Разработки", f"{df_m:.1f}%", f"Мед: {df_med:.1f}% | P85: {df_p85:.1f}%")

                st.markdown("---")
                st.markdown("##### Сводная таблица по разработке (в днях)")
                dev_cols = [
                    "Задача",
                    "К разработке (д.)",
                    "В разработке (д.)",
                    "К ревью (разработка) (д.)",
                    "Код ревью (д.)",
                    "Цикл Разработки (д.)",
                    "Flow Разработки (%)",
                ]

                dev_metrics_only = [col for col in dev_cols if col != "Задача"]
                dev_table_filtered = summary_df[dev_cols][
                    (summary_df[dev_metrics_only] > 0).any(axis=1)
                ]

                if not dev_table_filtered.empty:
                    st.dataframe(dev_table_filtered, use_container_width=True, hide_index=True)
                else:
                    st.info("В выбранном периоде нет задач с активностью на этапе разработки.")

                if gemini_key and st.button("🚀 ИИ-аудит разработки (CrewAI)", key="btn_dev_ai"):
                    with st.spinner("Агенты анализируют метрики разработки..."):
                        try:
                            gemini_llm = LLM(model="gemini/gemini-3.6-flash", api_key=gemini_key, temperature=0.2)
                            dev_lead = Agent(role="Lead Software Architect", goal="Оценить скорость написания кода и очереди код-ревью", backstory="Senior Tech Lead.", llm=gemini_llm)
                            t_dev = Task(
                                description=f"Данные разработки (1 р.д. = {net_day_hours:.1f} ч):\nВ разработке ср={dw_m:.2f}д (P85={dw_p85:.2f}д), Очередь/Ревью={dq_m:.2f}д, Flow={df_m:.1f}%\nДай 3 рекомендации по оптимизации код-ревью и устранению задержек.",
                                expected_output="3 инженерные рекомендации.",
                                agent=dev_lead
                            )
                            res = Crew(agents=[dev_lead], tasks=[t_dev]).kickoff()
                            st.success("Аудит разработки завершен!")
                            st.markdown(res.raw)
                        except Exception as err:
                            st.error(f"Ошибка ИИ: {err}")

            with dev_sub2:
                if not dev_iter_df.empty:
                    dev_grp = dev_iter_df.groupby("Разработчик").agg(
                        tasks=("Задача", "nunique"), iters=("Итерация", "count"), days=("Раб. дней", "sum")
                    ).reset_index()
                    dev_grp["avg_per_task"] = (dev_grp["days"] / dev_grp["tasks"]).round(2)
                    dev_grp = dev_grp.rename(columns={"tasks": "Задач (шт)", "iters": "Подходов (шт)", "days": "Суммарно (д.)", "avg_per_task": "Среднее на задачу (д.)"})
                    st.dataframe(dev_grp, use_container_width=True, hide_index=True)
                else:
                    st.info("Нет данных по разработчикам в данном периоде.")

            with dev_sub3:
                st.markdown("##### 🔍 Анализ Код Ревью («К ревью (разработка)» и «Код ревью»)")
                if not dev_rev_df.empty:
                    rev_summary = dev_rev_df.groupby("Этап ревью").agg(
                        tasks=("Задача", "nunique"), total_days=("Длительность (д.)", "sum"), avg_days=("Длительность (д.)", "mean")
                    ).reset_index()
                    rev_summary = rev_summary.rename(columns={"tasks": "Задач (шт)", "total_days": "Суммарно (д.)", "avg_days": "Среднее (д.)"})
                    st.dataframe(rev_summary, use_container_width=True, hide_index=True)
                    st.markdown("###### Лог событий код-ревью:")
                    st.dataframe(dev_rev_df, use_container_width=True, hide_index=True)
                else:
                    st.info("Нет зафиксированных переходов в этапы код-ревью.")

            with dev_sub4:
                render_searchable_log(dev_iter_df, "Задача", "Журнал работы разработчиков («В разработке»)", "dev_iterations.csv", "dev_log")

        # ==================================================================
        # 9. АУДИТ АНАЛИТИКИ
        # ==================================================================
        with tab_an:
            st.subheader("📐 Комплексный аудит аналитики")
            an_sub1, an_sub2, an_sub3, an_sub4 = st.tabs([
                "📊 Метрики и Flow Аналитики",
                "👥 Аналитика по аналитикам",
                "🔍 Анализ Ревью Аналитики",
                "📋 Журнал итераций Аналитики",
            ])

            with an_sub1:
                an_stat_df = summary_df[summary_df["В аналитике (д.)"] > 0].copy() if only_qa_active else summary_df.copy()
                aw_m, aw_med, aw_p85, _ = calc_stats(an_stat_df.get("В аналитике (д.)", pd.Series(dtype=float)))
                aq_m, aq_med, aq_p85, _ = calc_stats(an_stat_df.get("Очередь/Ревью Аналитики (д.)", pd.Series(dtype=float)))
                ac_m, ac_med, ac_p85, _ = calc_stats(an_stat_df.get("Цикл Аналитики (д.)", pd.Series(dtype=float)))
                af_m, af_med, af_p85, _ = calc_stats(an_stat_df.get("Flow Аналитики (%)", pd.Series(dtype=float)))

                a1, a2, a3, a4 = st.columns(4)
                a1.metric("В аналитике", f"{aw_m:.2f} д.", f"Мед: {aw_med:.2f} | P85: {aw_p85:.2f}")
                a2.metric("Очередь + Ревью Аналитики", f"{aq_m:.2f} д.", f"Мед: {aq_med:.2f} | P85: {aq_p85:.2f}", delta_color="inverse")
                a3.metric("Цикл Аналитики", f"{ac_m:.2f} д.", f"Мед: {ac_med:.2f} | P85: {ac_p85:.2f}")
                a4.metric("Flow Аналитики", f"{af_m:.1f}%", f"Мед: {af_med:.1f}% | P85: {af_p85:.1f}%")

                st.markdown("---")
                st.markdown("##### Сводная таблица по аналитике (в днях)")
                an_cols = [
                    "Задача",
                    "К аналитике (д.)",
                    "В аналитике (д.)",
                    "К ревью (аналитика) (д.)",
                    "Ревью аналитики (д.)",
                    "Цикл Аналитики (д.)",
                    "Flow Аналитики (%)",
                ]

                an_metrics_only = [col for col in an_cols if col != "Задача"]
                an_table_filtered = summary_df[an_cols][
                    (summary_df[an_metrics_only] > 0).any(axis=1)
                ]

                if not an_table_filtered.empty:
                    st.dataframe(an_table_filtered, use_container_width=True, hide_index=True)
                else:
                    st.info("В выбранном периоде нет задач с активностью на этапе аналитики.")

                if gemini_key and st.button("🚀 ИИ-аудит аналитики (CrewAI)", key="btn_an_ai"):
                    with st.spinner("Агенты анализируют подготовку требований..."):
                        try:
                            gemini_llm = LLM(model="gemini/gemini-3.6-flash", api_key=gemini_key, temperature=0.2)
                            an_lead = Agent(role="Lead Business Systems Analyst", goal="Ускорить подготовку требований и минимизировать застревание в ревью", backstory="Lead SA/BA.", llm=gemini_llm)
                            t_an = Task(
                                description=f"Данные этапа аналитики (1 р.д. = {net_day_hours:.1f} ч):\nВ аналитике ср={aw_m:.2f}д (P85={aw_p85:.2f}д), Очередь/Ревью={aq_m:.2f}д, Flow={af_m:.1f}%\nСформулируй 3 рекомендации по сокращению времени согласования ТЗ.",
                                expected_output="3 рекомендации для аналитиков.",
                                agent=an_lead
                            )
                            res = Crew(agents=[an_lead], tasks=[t_an]).kickoff()
                            st.success("Аудит аналитики завершен!")
                            st.markdown(res.raw)
                        except Exception as err:
                            st.error(f"Ошибка ИИ: {err}")

            with an_sub2:
                if not an_iter_df.empty:
                    an_grp = an_iter_df.groupby("Аналитик").agg(
                        tasks=("Задача", "nunique"), iters=("Итерация", "count"), days=("Раб. дней", "sum")
                    ).reset_index()
                    an_grp["avg_per_task"] = (an_grp["days"] / an_grp["tasks"]).round(2)
                    an_grp = an_grp.rename(columns={"tasks": "Задач (шт)", "iters": "Подходов (шт)", "days": "Суммарно (д.)", "avg_per_task": "Среднее на задачу (д.)"})
                    st.dataframe(an_grp, use_container_width=True, hide_index=True)
                else:
                    st.info("Нет данных по аналитикам в данном периоде.")

            with an_sub3:
                st.markdown("##### 🔍 Анализ Ревью Аналитики («К ревью (аналитика)» и «Ревью аналитики»)")
                if not an_rev_df.empty:
                    an_rev_summary = an_rev_df.groupby("Этап ревью").agg(
                        tasks=("Задача", "nunique"), total_days=("Длительность (д.)", "sum"), avg_days=("Длительность (д.)", "mean")
                    ).reset_index()
                    an_rev_summary = an_rev_summary.rename(columns={"tasks": "Задач (шт)", "total_days": "Суммарно (д.)", "avg_days": "Среднее (д.)"})
                    st.dataframe(an_rev_summary, use_container_width=True, hide_index=True)
                    st.markdown("###### Лог событий ревью аналитики:")
                    st.dataframe(an_rev_df, use_container_width=True, hide_index=True)
                else:
                    st.info("Нет зафиксированных переходов в этапы ревью аналитики.")

            with an_sub4:
                render_searchable_log(an_iter_df, "Задача", "Журнал работы аналитиков («В аналитике»)", "analytics_iterations.csv", "an_log")

        # ==================================================================
        # 10. ДЕТАЛИЗАЦИЯ ПО ЗАДАЧЕ
        # ==================================================================
        with tab_task:
            selected_task = st.selectbox("Выберите задачу для детализации:", unique_tasks)
            task_info = summary_df[summary_df["Задача"] == selected_task].iloc[0]

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Полный Lead Time", f"{task_info['Полный Lead Time (д.)']} д.")
            c2.metric("Всего очередей", f"{task_info['Всего очередей (д.)']} д.", delta_color="inverse")
            c3.metric("Чистая работа", f"{task_info['Чистая работа (д.)']} д.")
            c4.metric("Flow Efficiency", f"{task_info['Сквозной Flow Efficiency (%)']}%")

            task_status_values = [task_info[f"{st_name} (д.)"] for st_name in ALL_TRACKED_STATUSES if task_info.get(f"{st_name} (д.)", 0) > 0]
            task_status_labels = [st_name for st_name in ALL_TRACKED_STATUSES if task_info.get(f"{st_name} (д.)", 0) > 0]

            if task_status_values:
                fig_task_pie = px.pie(
                    names=task_status_labels,
                    values=task_status_values,
                    title=f"Структура времени задачи {selected_task} ({task_info.get('Тип задачи', '')} | {task_info.get('Приоритет', '')}) по статусам",
                    hole=0.45,
                )
                fig_task_pie.update_layout(height=350)
                st.plotly_chart(fig_task_pie, use_container_width=True)