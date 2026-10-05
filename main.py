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
from db import (
    get_all_events, get_summary_stats, clear_database, get_db_fingerprint
)
from auth import (
    render_login_page, render_user_info_sidebar
)
from access_control import (
    get_available_tabs, get_tab_labels,
    get_user_role, filter_summary_by_role, filter_iter_df_by_role
)

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


def run_streamlit_app():
    """Точка входа для Streamlit. Вызывается только при запуске через `streamlit run main.py`."""
    import streamlit as st
    from db import make_file_hash, load_dataframe_to_db, is_file_loaded

    st.set_page_config(page_title="Team Process Analytics", page_icon="📊", layout="wide")
    st.title("📊 Комплексный процессный аудит команды")

    # --- АУТЕНТИФИКАЦИЯ (сразу после title) ---
    if not render_login_page():
        st.stop()

    user_name = st.session_state.user_name
    user_role = st.session_state.user_role
    is_admin = user_role == "admin"

    with st.sidebar:
        render_user_info_sidebar()
        st.header("⚙️ Параметры анализа")
        work_start_h = st.number_input("Начало дня (час)", 0, 23, 9)
        work_end_h = st.number_input("Конец дня (час)", 0, 23, 18)
        deduct_hours = st.number_input("Обед + созвоны (часов)", 0.0, 8.0, 2.0)
        day_window = max(1.0, float(work_end_h - work_start_h))
        net_day_hours = max(1.0, day_window - deduct_hours)
        net_ratio = net_day_hours / day_window

        st.markdown("---")
        st.header("🗄️ База данных (DuckDB)")
        stats = get_summary_stats()
        st.metric("Загружено строк", f"{stats['total_rows']:,}")
        st.metric("Уникальных задач", f"{stats['unique_tasks']:,}")
        st.metric("Файлов загружено", f"{stats['loaded_files']:,}")
        if stats['last_load']:
            st.caption(f"Последняя загрузка: {stats['last_load']}")

        if is_admin:
            if st.button("🗑️ Очистить базу", type="secondary"):
                clear_database()
                st.success("База очищена")
                st.rerun()

    # Читаем все события из DuckDB для аналитики
    full_raw_df = get_all_events()

    # Загрузка файлов — только для админа
    if is_admin:
        uploaded_files = st.file_uploader("Загрузите CSV-файлы журнала задач", type=["csv"], accept_multiple_files=True)

        if uploaded_files:
            dfs = []
            validation_errors = []
            total_new_rows = 0
            
            for f in uploaded_files:
                f.seek(0)
                file_bytes = f.read()
                file_hash = make_file_hash(file_bytes)
                
                # Проверка: файл уже загружен?
                if is_file_loaded(file_hash):
                    st.info(f"⏭ {f.name} — уже загружен ранее (пропущен)")
                    continue
                
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
                
                # Загрузка в DuckDB с дедупликацией
                from db import load_dataframe_to_db
                new_rows = load_dataframe_to_db(df_temp, f.name, file_hash)
                total_new_rows += new_rows
                st.success(f"✅ {f.name}: добавлено {new_rows} новых строк")
            
            if validation_errors:
                for err in validation_errors:
                    st.error(err)
                st.stop()

            if total_new_rows > 0:
                st.rerun()

    if full_raw_df.empty:
        if is_admin:
            st.info("📭 База пуста. Загрузите CSV-файлы для начала анализа.")
        else:
            st.warning("📭 Данных нет. Обратитесь к администратору для загрузки данных.")
        st.stop()

    # Нормализация колонок для pipeline
    if "task_identifier" not in full_raw_df.columns:
        full_raw_df["task_identifier"] = full_raw_df["task_id"]

    (
        global_summary_df,
        all_qa_iters,
        all_dev_iters,
        all_an_iters,
        all_dev_revs,
        all_an_revs,
        all_reworks,
        all_qa_waits,
    ) = process_all_tasks_cached(
        get_db_fingerprint(), work_start_h, work_end_h, net_ratio, net_day_hours
    )

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

    # Сохраняем оригинальные active_tids для вкладки детализации (показать все задачи)
    all_active_tids = active_tids.copy()

    summary_df = global_summary_df[global_summary_df["Задача"].isin(active_tids)].copy()
    qa_iter_df = all_qa_iters[all_qa_iters["Задача"].isin(active_tids)].copy() if not all_qa_iters.empty else all_qa_iters
    dev_iter_df = all_dev_iters[all_dev_iters["Задача"].isin(active_tids)].copy() if not all_dev_iters.empty else all_dev_iters
    an_iter_df = all_an_iters[all_an_iters["Задача"].isin(active_tids)].copy() if not all_an_iters.empty else all_an_iters
    dev_rev_df = all_dev_revs[all_dev_revs["Задача"].isin(active_tids)].copy() if not all_dev_revs.empty else all_dev_revs
    an_rev_df = all_an_revs[all_an_revs["Задача"].isin(active_tids)].copy() if not all_an_revs.empty else all_an_revs
    reworks_df = all_reworks[all_reworks["Задача"].isin(active_tids)].copy() if not all_reworks.empty else all_reworks
    qa_wait_df = all_qa_waits[all_qa_waits["Задача"].isin(active_tids)].copy() if not all_qa_waits.empty else all_qa_waits

    user_name = st.session_state.user_name
    user_role = st.session_state.user_role
    available_tabs = get_available_tabs(user_role)
    tab_labels = get_tab_labels()

    if summary_df.empty:
        st.warning(f"⚠️ В выбранном периоде ({sel_label}) нет движения по статусам.")
    else:
        # Фильтруем данные по роли
        summary_df = filter_summary_by_role(summary_df, user_role, user_name)
        qa_iter_df = filter_iter_df_by_role(qa_iter_df, user_role, user_name)
        dev_iter_df = filter_iter_df_by_role(dev_iter_df, user_role, user_name)
        an_iter_df = filter_iter_df_by_role(an_iter_df, user_role, user_name)

        # Динамически создаём вкладки на основе роли
        tabs_to_render = [tab for tab in [
            "overview", "periods", "estimates", "deadlines", "types", "priorities",
            "qa", "dev", "analytics", "detail"
        ] if tab in available_tabs]

        tab_objects = st.tabs([tab_labels[t] for t in tabs_to_render])

        for tab_key, tab_obj in zip(tabs_to_render, tab_objects):
            with tab_obj:
                if tab_key == "overview":
                    render_overview_tab(summary_df, net_day_hours=net_day_hours)

                elif tab_key == "periods":
                    render_periods_tab(monthly_sprints_list, quarter_list, full_raw_df, global_summary_df)

                elif tab_key == "estimates":
                    render_estimates_tab(summary_df, qa_iter_df, dev_iter_df, an_iter_df)

                elif tab_key == "deadlines":
                    render_deadlines_tab(summary_df)

                elif tab_key == "types":
                    render_types_tab(summary_df)

                elif tab_key == "priorities":
                    render_priorities_tab(summary_df)

                elif tab_key == "qa":
                    render_role_tab(
                        role_title="QA",
                        work_status_col="В тестировании (дни)",
                        queue_status_col="Очередь ожидания QA (дни)",
                        cycle_col="Циклтайм QA (дни)",
                        flow_col="Flow Efficiency QA (%)",
                        table_cols=["Задача", "В тестировании (дни)", "Очередь ожидания QA (дни)", "Циклтайм QA (дни)", "Flow Efficiency QA (%)"],
                        iter_df=qa_iter_df,
                        rev_df=pd.DataFrame(),
                        wait_df=qa_wait_df,
                        summary_df=summary_df,
                        actor_col_name="Исполнитель",
                        net_day_hours=net_day_hours,
                        reworks_df=reworks_df,
                        role_key="qa",
                        start_date=None if period_mode == "Весь период" else start_date,
                        end_date=None if period_mode == "Весь период" else end_date,
                        work_start_h=work_start_h,
                        work_end_h=work_end_h,
                        net_ratio=net_ratio,
                        global_summary_df=global_summary_df,
                    )

                elif tab_key == "dev":
                    render_role_tab(
                        role_title="Разработка",
                        work_status_col="В разработке (д.)",
                        queue_status_col="Очередь/Код Ревью Dev (д.)",
                        cycle_col="Цикл Разработки (д.)",
                        flow_col="Flow Разработки (%)",
                        table_cols=["Задача", "К разработке (д.)", "В разработке (д.)", "К ревью (разработка) (д.)", "Ревью кода (д.)", "Цикл Разработки (д.)", "Flow Разработки (%)"],
                        iter_df=dev_iter_df,
                        rev_df=dev_rev_df,
                        summary_df=summary_df,
                        actor_col_name="Разработчик",
                        net_day_hours=net_day_hours,
                        role_key="dev",
                        start_date=None if period_mode == "Весь период" else start_date,
                        end_date=None if period_mode == "Весь период" else end_date,
                        work_start_h=work_start_h,
                        work_end_h=work_end_h,
                        net_ratio=net_ratio,
                        wait_col="К разработке (д.)",
                        rev_col="Ревью кода (д.)",
                        global_summary_df=global_summary_df,
                    )

                elif tab_key == "analytics":
                    render_role_tab(
                        role_title="Аналитика",
                        work_status_col="В аналитике (д.)",
                        queue_status_col="Очередь/Ревью Аналитики (д.)",
                        cycle_col="Цикл Аналитики (д.)",
                        flow_col="Flow Аналитики (%)",
                        table_cols=["Задача", "К аналитике (д.)", "В аналитике (д.)", "К ревью (аналитика) (д.)", "Ревью аналитики (д.)", "Цикл Аналитики (д.)", "Flow Аналитики (%)"],
                        iter_df=an_iter_df,
                        rev_df=an_rev_df,
                        summary_df=summary_df,
                        actor_col_name="Аналитик",
                        net_day_hours=net_day_hours,
                        role_key="an",
                        start_date=None if period_mode == "Весь период" else start_date,
                        end_date=None if period_mode == "Весь период" else end_date,
                        work_start_h=work_start_h,
                        work_end_h=work_end_h,
                        net_ratio=net_ratio,
                        wait_col="К аналитике (д.)",
                        rev_col="Ревью аналитики (д.)",
                        global_summary_df=global_summary_df,
                    )

                elif tab_key == "detail":
                    # Для детализации используем global_summary_df и все задачи (не отфильтрованные по роли)
                    render_task_detail_tab(global_summary_df, all_active_tids)


if __name__ == "__main__":
    # Запуск только при прямом вызове python main.py (не при импорте в тестах)
    import streamlit as st
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    
    if get_script_run_ctx() is not None:
        run_streamlit_app()