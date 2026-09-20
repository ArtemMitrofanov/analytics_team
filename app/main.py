"""main.py — Главная точка входа Streamlit приложения."""
import sys
from pathlib import Path

# Гарантируем регистрацию путей поиска модулей
APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
for path in (str(APP_DIR), str(PROJECT_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

import pandas as pd
import streamlit as st

from config import MONTH_NAMES_RU
from data.pipeline import process_all_tasks_cached
from ui.tabs.overview import render_overview_tab
from ui.tabs.periods import render_periods_tab
from ui.tabs.estimates import render_estimates_tab
from ui.tabs.deadlines import render_deadlines_tab
from ui.tabs.types import render_types_tab
from ui.tabs.priorities import render_priorities_tab
from ui.tabs.role_view import render_role_tab
from ui.tabs.task_detail import render_task_detail_tab

REQUIRED_COLUMNS = {
    "timestamp", "changed_value", "added_values", "removed_values", "author_full_name"
}
OPTIONAL_COLUMNS = {"issue_id", "iissue_id", "activity_type"}

def validate_csv_schema(df: pd.DataFrame, filename: str) -> tuple[bool, list[str]]:
    """Проверяет наличие обязательных колонок в CSV. Возвращает (is_valid, errors)."""
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        return False, [f"{filename}: отсутствуют обязательные колонки: {', '.join(sorted(missing))}"]
    return True, []

st.set_page_config(page_title="Team Process Analytics", page_icon="📊", layout="wide")
st.title("📊 Комплексный процессный аудит команды")

with st.sidebar:
    st.header("⚙️ Параметры анализа")
    work_start_h = st.number_input("Начало дня (час)", 0, 23, 9)
    work_end_h = st.number_input("Конец дня (час)", 0, 23, 18)
    deduct_hours = st.number_input("Обед + созвоны (часов)", 0.0, 8.0, 2.0)
    day_window = max(1.0, float(work_end_h - work_start_h))
    net_day_hours = max(1.0, day_window - deduct_hours)
    net_ratio = net_day_hours / day_window

uploaded_files = st.file_uploader("Загрузите CSV-файлы журнала задач", type=["csv"], accept_multiple_files=True)

if uploaded_files:
    dfs = []
    validation_errors = []
    for f in uploaded_files:
        f.seek(0)
        try:
            df_temp = pd.read_csv(f, on_bad_lines="skip", low_memory=False)
        except Exception:
            f.seek(0)
            df_temp = pd.read_csv(f, sep=None, engine="python", on_bad_lines="skip")
        
        is_valid, errors = validate_csv_schema(df_temp, f.name)
        if not is_valid:
            validation_errors.extend(errors)
            continue
        
        df_temp["task_identifier"] = df_temp.get("issue_id", df_temp.get("iissue_id", f.name.replace(".csv", "")))
        dfs.append(df_temp)
    
    if validation_errors:
        for err in validation_errors:
            st.error(err)
        st.stop()

    full_raw_df = pd.concat(dfs, ignore_index=True)
    full_raw_df["timestamp"] = pd.to_datetime(full_raw_df["timestamp"])

    (
        global_summary_df,
        all_qa_iters,
        all_dev_iters,
        all_an_iters,
        all_dev_revs,
        all_an_revs,
        all_reworks,
    ) = process_all_tasks_cached(full_raw_df, work_start_h, work_end_h, net_ratio, net_day_hours)

    periods_m = sorted(full_raw_df["timestamp"].dt.to_period("M").unique())
    monthly_sprints_list = [
        {
            "period_name": f"{MONTH_NAMES_RU.get(p.month, str(p.month))} {p.year}",
            "start_date": p.start_time.date(),
            "end_date": p.end_time.date()
        }
        for p in periods_m
    ]
    sprint_lookup = {
        f"Спринт: {item['period_name']}": (item["start_date"], item["end_date"])
        for item in monthly_sprints_list
    }

    periods_q = sorted(full_raw_df["timestamp"].dt.to_period("Q").unique())
    quarter_list = [
        {
            "period_name": f"Q{q.quarter} {q.year}",
            "start_date": q.start_time.date(),
            "end_date": q.end_time.date()
        }
        for q in periods_q
    ]
    quarter_lookup = {
        f"Квартал: {item['period_name']}": (item["start_date"], item["end_date"])
        for item in quarter_list
    }

    with st.sidebar:
        st.markdown("---")
        period_mode = st.radio(
            "Группировка периода:",
            options=["Весь период", "По месяцам (Спринты)", "По кварталам", "Пользовательский диапазон"],
            index=0,
        )
        if period_mode == "По месяцам (Спринты)":
            sel_label = st.selectbox("Выберите спринт:", options=list(sprint_lookup.keys()))
            start_date, end_date = sprint_lookup[sel_label]
        elif period_mode == "По кварталам":
            sel_label = st.selectbox("Выберите квартал:", options=list(quarter_lookup.keys()))
            start_date, end_date = quarter_lookup[sel_label]
        elif period_mode == "Пользовательский диапазон":
            min_d, max_d = full_raw_df["timestamp"].min().date(), full_raw_df["timestamp"].max().date()
            d_range = st.date_input("Диапазон", value=(min_d, max_d))
            start_date, end_date = d_range if isinstance(d_range, tuple) and len(d_range) == 2 else (min_d, max_d)
            sel_label = f"{start_date} — {end_date}"
        else:
            start_date, end_date = full_raw_df["timestamp"].min().date(), full_raw_df["timestamp"].max().date()
            sel_label = "Весь период"

    if period_mode == "Весь период":
        active_tids = global_summary_df["Задача"].dropna().unique()
    else:
        active_events = full_raw_df[
            (full_raw_df["timestamp"].dt.date >= start_date)
            & (full_raw_df["timestamp"].dt.date <= end_date)
            & (full_raw_df["changed_value"].isin(["Текущий статус", "State"]))
        ]
        active_tids = active_events["task_identifier"].dropna().unique()

    summary_df = global_summary_df[global_summary_df["Задача"].isin(active_tids)].copy()
    qa_iter_df = all_qa_iters[all_qa_iters["Задача"].isin(active_tids)].copy() if not all_qa_iters.empty else all_qa_iters
    dev_iter_df = all_dev_iters[all_dev_iters["Задача"].isin(active_tids)].copy() if not all_dev_iters.empty else all_dev_iters
    an_iter_df = all_an_iters[all_an_iters["Задача"].isin(active_tids)].copy() if not all_an_iters.empty else all_an_iters
    dev_rev_df = all_dev_revs[all_dev_revs["Задача"].isin(active_tids)].copy() if not all_dev_revs.empty else all_dev_revs
    an_rev_df = all_an_revs[all_an_revs["Задача"].isin(active_tids)].copy() if not all_an_revs.empty else all_an_revs
    reworks_df = all_reworks[all_reworks["Задача"].isin(active_tids)].copy() if not all_reworks.empty else all_reworks

    if summary_df.empty:
        st.warning(f"⚠️ В выбранном периоде ({sel_label}) нет движения по статусам.")
    else:
        # ЕДИНСТВЕННЫЙ блок объявления всех 10 вкладок
        t_overview, t_periods, t_est, t_deadlines, t_types, t_prio, t_qa, t_dev, t_an, t_detail = st.tabs([
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

        with t_overview:
            render_overview_tab(summary_df, net_day_hours=net_day_hours)

        with t_periods:
            render_periods_tab(monthly_sprints_list, quarter_list, full_raw_df, global_summary_df)

        with t_est:
            render_estimates_tab(summary_df, qa_iter_df, dev_iter_df, an_iter_df)

        with t_deadlines:
            render_deadlines_tab(summary_df)

        with t_types:
            render_types_tab(summary_df)

        with t_prio:
            render_priorities_tab(summary_df)

        with t_qa:
            render_role_tab(
                role_title="QA",
                work_status_col="В тестировании (дни)",
                queue_status_col="Очередь ожидания QA (дни)",
                cycle_col="Циклтайм QA (дни)",
                flow_col="Flow Efficiency QA (%)",
                table_cols=["Задача", "В тестировании (дни)", "Очередь ожидания QA (дни)", "Циклтайм QA (дни)", "Flow Efficiency QA (%)"],
                iter_df=qa_iter_df,
                rev_df=pd.DataFrame(),
                summary_df=summary_df,
                actor_col_name="Исполнитель",
                net_day_hours=net_day_hours,
                reworks_df=reworks_df,
            )

        with t_dev:
            render_role_tab(
                role_title="Разработка",
                work_status_col="В разработке (д.)",
                queue_status_col="Очередь/Код Ревью Dev (д.)",
                cycle_col="Цикл Разработки (д.)",
                flow_col="Flow Разработки (%)",
                table_cols=["Задача", "К разработке (д.)", "В разработке (д.)", "Цикл Разработки (д.)", "Flow Разработки (%)"],
                iter_df=dev_iter_df,
                rev_df=dev_rev_df,
                summary_df=summary_df,
                actor_col_name="Разработчик",
                net_day_hours=net_day_hours,
            )

        with t_an:
            render_role_tab(
                role_title="Аналитика",
                work_status_col="В аналитике (д.)",
                queue_status_col="Очередь/Ревью Аналитики (д.)",
                cycle_col="Цикл Аналитики (д.)",
                flow_col="Flow Аналитики (%)",
                table_cols=["Задача", "К аналитике (д.)", "В аналитике (д.)", "Цикл Аналитики (д.)", "Flow Аналитики (%)"],
                iter_df=an_iter_df,
                rev_df=an_rev_df,
                summary_df=summary_df,
                actor_col_name="Аналитик",
                net_day_hours=net_day_hours,
            )

        with t_detail:
            render_task_detail_tab(summary_df, active_tids)