"""main.py — Главная точка входа Streamlit приложения."""
import re
import sys
from collections import Counter
from hashlib import sha256
from pathlib import Path
from time import perf_counter

# Гарантируем регистрацию путей поиска модулей
APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
for path in (str(APP_DIR), str(PROJECT_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

import pandas as pd

from config import (
    CREATION_SIZE_PROJECT, DEFAULT_DEDUCT_HOURS, DEFAULT_WORK_END, DEFAULT_WORK_START,
    MONTH_NAMES_RU, TEAMS, team_display_label,
)
from data.pipeline import PIPELINE_VERSION, process_all_tasks_cached
from data.workflow import status_event_mask
from ui.tabs.dashboard import render_dashboard_tab
from ui.tabs.team_comparison import render_team_comparison
from ui.tabs.overview import render_overview_tab
from ui.tabs.periods import render_periods_tab
from ui.tabs.estimates import render_estimates_tab
from ui.tabs.deadlines import render_deadlines_tab
from ui.tabs.types import render_types_tab
from ui.tabs.priorities import render_priorities_tab
from ui.tabs.role_view import render_role_tab
from ui.tabs.task_detail import render_task_detail_tab
from ui.bento import inject_theme, render_theme_toggle
from db import (
    get_all_events, get_event_months, get_summary_stats, clear_database, get_db_fingerprint, get_dsn,
    create_team, delete_team, get_team_display_names, get_teams, rename_team,
)
from auth import (
    render_login_page, render_user_info_sidebar
)
from access_control import (
    get_available_tabs, get_tab_labels,
    get_available_team_ids, filter_summary_by_role, filter_iter_df_by_role
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


def team_name_from_issue_id(frame: pd.DataFrame) -> str | None:
    if "issue_id" not in frame:
        return None
    for issue_id in frame["issue_id"].dropna():
        value = str(issue_id).strip()
        if value:
            match = re.fullmatch(r"([^\s]+)-[0-9]+", value)
            return match[1] if match else None
    return None


def run_streamlit_app():
    """Точка входа для Streamlit. Вызывается только при запуске через `streamlit run main.py`."""
    run_started = perf_counter()
    timings: dict[str, float] = {}

    import streamlit as st
    from db import WrongTeamImport, is_file_loaded, load_dataframe_to_db, make_file_hash

    st.set_page_config(
        page_title="Team Process Analytics",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_theme()
    st.title("📊 Комплексный процессный аудит")

    # --- АУТЕНТИФИКАЦИЯ (сразу после title) ---
    if not render_login_page():
        st.stop()

    user_name = st.session_state.user_name
    user_role = st.session_state.user_role
    is_admin = user_role == "admin"
    database_key = sha256(get_dsn().encode()).hexdigest()

    _, theme_col = st.columns([6, 1])
    with theme_col:
        render_theme_toggle()

    teams = get_teams()
    team_ids = get_available_team_ids(user_name, teams)
    if not team_ids and not is_admin:
        with st.sidebar:
            render_user_info_sidebar()
        st.warning("У вашей учётной записи нет доступа к командам.")
        st.stop()
    imported_names = get_team_display_names(team_ids)
    team_names = {
        team_id: (
            team_display_label(teams[team_id], imported_names.get(team_id))
            if team_id in TEAMS else teams[team_id].name
        )
        for team_id in team_ids
    }
    display_names = team_names
    name_counts = Counter(team_names.values())
    team_names = {
        team_id: f"{name} ({team_id})" if name_counts[name] > 1 else name
        for team_id, name in team_names.items()
    }

    available_tabs = get_available_tabs(user_role)
    tab_labels = get_tab_labels()

    # Динамически создаём навигацию на основе роли
    tabs_to_render = [tab for tab in [
        "dashboard", "overview", "periods", "estimates", "deadlines", "types", "priorities",
        "qa", "dev", "analytics", "detail"
    ] if tab in available_tabs]

    nav_labels = [tab_labels[t] for t in tabs_to_render]
    can_compare = "comparison" in available_tabs
    comparing = can_compare and st.session_state.get("show_team_comparison", False)
    selected_label = st.session_state.get("main_nav", nav_labels[0])
    if selected_label not in nav_labels:
        selected_label = nav_labels[0]
    if not comparing and st.session_state.get("main_nav") != selected_label:
        st.session_state.main_nav = selected_label

    with st.sidebar:
        render_user_info_sidebar()
        preferred_team = st.session_state.pop("preferred_team", None)
        if preferred_team in team_ids:
            st.session_state.team_selector = preferred_team
        elif st.session_state.get("team_selector") not in team_ids:
            st.session_state.team_selector = team_ids[0] if team_ids else None
        team_id = st.selectbox(
            "Команда", team_ids, index=None, format_func=team_names.__getitem__, key="team_selector",
            disabled=not team_ids,
        )
        team_notice = st.session_state.pop("team_notice", None)
        if team_notice:
            st.success(team_notice)
        if is_admin:
            with st.expander("Создать команду"):
                with st.form("create_team"):
                    name = st.text_input(
                        "Название", max_chars=100,
                        help="Если оставить пустым, подставится название из словаря или префикс.",
                    )
                    project = st.text_input("Префикс issue_id", placeholder="Finance", max_chars=100)
                    subsystem = st.text_input(
                        "Subsystem (необязательно)", placeholder="МСФО. п00272", max_chars=200,
                    )
                    submitted = st.form_submit_button("Создать")
                if submitted:
                    try:
                        created_id = create_team(user_name, name, project, subsystem)
                    except (ValueError, PermissionError) as exc:
                        st.warning(str(exc))
                    else:
                        st.session_state.preferred_team = created_id
                        st.session_state.team_notice = "Команда создана."
                        st.session_state.main_nav = tab_labels["dashboard"]
                        st.session_state.show_team_comparison = False
                        st.rerun()
        if is_admin and team_id is not None:
            with st.expander("Управление командой"):
                with st.form(f"rename_team_{team_id}", clear_on_submit=True):
                    name = st.text_input("Название команды", value=display_names[team_id], max_chars=100)
                    save_name = st.form_submit_button("Сохранить название")
                if save_name:
                    try:
                        rename_team(user_name, team_id, name)
                    except (ValueError, PermissionError) as exc:
                        st.warning(str(exc))
                    else:
                        st.session_state.preferred_team = team_id
                        st.session_state.team_notice = "Название сохранено."
                        st.rerun()

                with st.form(f"delete_team_{team_id}", clear_on_submit=True):
                    confirmed = st.checkbox(f"Подтверждаю удаление команды «{team_names[team_id]}» и всех её данных")
                    remove_team = st.form_submit_button("Удалить команду")
                if remove_team:
                    if not confirmed:
                        st.warning("Подтвердите удаление команды и её данных.")
                    else:
                        try:
                            deleted_rows = delete_team(user_name, team_id)
                        except (ValueError, PermissionError) as exc:
                            st.warning(str(exc))
                        else:
                            st.session_state.team_notice = (
                                f"Команда «{team_names[team_id]}» удалена. Удалено строк: {deleted_rows:,}."
                            )
                            st.rerun()
        if can_compare and team_ids:
            if comparing:
                next_navigation = {
                    "show_team_comparison": False,
                    "main_nav": st.session_state.get("return_team_section", nav_labels[0]),
                }
            else:
                next_navigation = {
                    "show_team_comparison": True,
                    "return_team_section": selected_label,
                }
            st.button(
                "Вернуться к команде" if comparing else tab_labels["comparison"],
                use_container_width=True,
                on_click=st.session_state.update,
                args=(next_navigation,),
            )

    if team_id is None:
        st.info("Создайте команду в боковой панели, чтобы начать работу.")
        return

    if comparing:
        def comparison_summary(compared_id: str) -> pd.DataFrame:
            window = DEFAULT_WORK_END - DEFAULT_WORK_START
            net_hours = window - DEFAULT_DEDUCT_HOURS
            return process_all_tasks_cached(
                get_db_fingerprint(team_id=compared_id),
                DEFAULT_WORK_START, DEFAULT_WORK_END, net_hours / window, net_hours,
                pipeline_version=PIPELINE_VERSION, database_key=database_key,
                team_id=compared_id, core_qa=teams[compared_id].qa,
            )[0]

        render_team_comparison(
            team_names,
            lambda selected_id: get_summary_stats(team_id=selected_id),
            comparison_summary,
            lambda selected_id: get_event_months(team_id=selected_id),
        )
        return

    nav_col, content_col = st.columns([1, 4])
    with nav_col:
        selected_label = st.radio(
            "Разделы",
            options=nav_labels,
            index=None,
            key="main_nav",
            label_visibility="collapsed",
        )

    selected_key = tabs_to_render[nav_labels.index(selected_label)]
    team = teams[team_id]
    team_name = team_names[team_id]
    stats_started = perf_counter()
    stats = get_summary_stats(team_id=team_id)
    timings["db_stats"] = perf_counter() - stats_started

    if selected_key == "dashboard":
        months_started = perf_counter()
        periods_m = pd.PeriodIndex(get_event_months(team_id=team_id), freq="M")
        timings["event_months"] = perf_counter() - months_started
        first_event, last_event = stats["earliest_event"], stats["latest_event"]
    else:
        full_raw_df = get_all_events(team_id=team_id)
        timestamps = full_raw_df["timestamp"]
        periods_m = sorted(timestamps.dt.to_period("M").unique())
        first_event, last_event = timestamps.min(), timestamps.max()

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

    periods_q = sorted({month.asfreq("Q") for month in periods_m})
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

    with content_col:
        st.header(team_name)

    with st.sidebar:
        period_mode = st.radio(
            "Группировка периода:",
            options=["Весь период", "По месяцам (Спринты)", "По кварталам", "Пользовательский диапазон"],
            index=0,
        )
        if len(periods_m) == 0 or first_event is None or last_event is None:
            start_date, end_date = None, None
            sel_label = "Весь период"
        elif period_mode == "По месяцам (Спринты)":
            sel_label = st.selectbox("Выберите спринт:", options=list(sprint_lookup.keys()))
            start_date, end_date = sprint_lookup[sel_label]
        elif period_mode == "По кварталам":
            sel_label = st.selectbox("Выберите квартал:", options=list(quarter_lookup.keys()))
            start_date, end_date = quarter_lookup[sel_label]
        elif period_mode == "Пользовательский диапазон":
            min_d, max_d = first_event.date(), last_event.date()
            d_range = st.date_input("Диапазон", value=(min_d, max_d))
            start_date, end_date = d_range if isinstance(d_range, tuple) and len(d_range) == 2 else (min_d, max_d)
            sel_label = f"{start_date} — {end_date}"
        else:
            start_date, end_date = first_event.date(), last_event.date()
            sel_label = "Весь период"

        st.markdown("---")
        st.header("⚙️ Параметры анализа")
        work_start_h = st.number_input("Начало дня (час)", 0, 23, team.work_start, key=f"work_start_{team_id}")
        work_end_h = st.number_input("Конец дня (час)", 0, 23, team.work_end, key=f"work_end_{team_id}")
        deduct_hours = st.number_input("Обед + созвоны (часов)", 0.0, 8.0, team.deduct_hours, key=f"deduct_{team_id}")
        day_window = max(1.0, float(work_end_h - work_start_h))
        net_day_hours = max(1.0, day_window - deduct_hours)
        net_ratio = net_day_hours / day_window

        st.markdown("---")
        st.header("Данные команды")
        st.metric("Загружено строк", f"{stats['total_rows']:,}")
        st.metric("Уникальных задач", f"{stats['unique_tasks']:,}")
        st.metric("Файлов загружено", f"{stats['loaded_files']:,}")
        if stats['last_load']:
            st.caption(f"Последняя загрузка: {stats['last_load']}")

        if is_admin:
            if st.button("🗑️ Очистить данные команды", type="secondary", key=f"clear_{team_id}"):
                clear_database(team_id=team_id)
                st.success("Данные команды удалены")
                st.rerun()

    if is_admin:
        with content_col:
            import_message = st.session_state.pop("team_import_message", None)
            if import_message:
                added, errors, warnings = import_message
                if added or not (errors or warnings):
                    st.success(f"Добавлено строк: {added}")
                for error in errors:
                    st.error(error)
                for warning in warnings:
                    st.warning(warning)
            with st.expander(f"Загрузка CSV · {team_name}"):
                with st.form(f"upload_{team_id}", clear_on_submit=True):
                    uploaded_files = st.file_uploader(
                        "CSV-файлы журнала задач", type=["csv"], accept_multiple_files=True,
                    )
                    submitted = st.form_submit_button("Загрузить в команду")

            if submitted and uploaded_files:
                errors = []
                warnings = []
                added = 0
                for file in uploaded_files:
                    file_hash = make_file_hash(file.getvalue())
                    if is_file_loaded(file_hash, team_id=team_id):
                        continue
                    try:
                        try:
                            frame = pd.read_csv(file, on_bad_lines="skip", low_memory=False)
                        except pd.errors.ParserError:
                            file.seek(0)
                            frame = pd.read_csv(file, sep=None, engine="python", on_bad_lines="skip")
                    except (UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
                        errors.append(f"{file.name}: {exc}")
                        continue
                    valid, validation_errors = validate_csv_schema(frame, file.name)
                    if not valid:
                        errors.extend(validation_errors)
                        continue
                    frame["task_identifier"] = frame.get(
                        "issue_id", frame.get("iissue_id", Path(file.name).stem)
                    )
                    try:
                        added += load_dataframe_to_db(
                            frame, file.name, file_hash, team_id=team_id,
                            team_name=team_name_from_issue_id(frame),
                        )
                    except WrongTeamImport as exc:
                        warnings.append(f"{file.name}: {exc}")
                st.session_state["team_import_message"] = (added, errors, warnings)
                st.rerun()

    if len(periods_m) == 0:
        if is_admin:
            st.info("📭 База пуста. Загрузите CSV-файлы для начала анализа.")
        else:
            st.warning("📭 Данных нет. Обратитесь к администратору для загрузки данных.")
        st.stop()

    fingerprint_started = perf_counter()
    db_fingerprint = get_db_fingerprint(team_id=team_id)
    timings["db_fingerprint"] = perf_counter() - fingerprint_started
    pipeline_started = perf_counter()
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
        db_fingerprint, work_start_h, work_end_h, net_ratio, net_day_hours,
        pipeline_version=PIPELINE_VERSION, database_key=database_key,
        team_id=team_id, core_qa=team.qa, _timings=timings,
    )
    timings["pipeline"] = perf_counter() - pipeline_started

    if selected_key == "dashboard":
        dashboard_started = perf_counter()
        with content_col:
            render_dashboard_tab(global_summary_df, data_months=periods_m, timings=timings)
        timings["dashboard"] = perf_counter() - dashboard_started
        timings["total"] = perf_counter() - run_started
        cache_status = "miss" if "pipeline_events" in timings else "hit"
        durations = " ".join(f"{stage}_ms={seconds * 1000:.1f}" for stage, seconds in timings.items())
        print(f"dashboard_perf cache={cache_status} {durations}", file=sys.stderr, flush=True)
        return

    # Нормализация колонок для фильтрации и вкладок
    if "task_identifier" not in full_raw_df.columns:
        full_raw_df["task_identifier"] = full_raw_df["task_id"]

    if period_mode == "Весь период":
        active_tids = global_summary_df["Задача"].dropna().unique()
    else:
        active_events = full_raw_df[
            (full_raw_df["timestamp"].dt.date >= start_date)
            & (full_raw_df["timestamp"].dt.date <= end_date)
            & status_event_mask(full_raw_df)
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

    if summary_df.empty and selected_key != "qa":
        with content_col:
            st.warning(f"⚠️ В выбранном периоде ({sel_label}) нет движения по статусам.")
    else:
        # Фильтруем данные по роли
        summary_df = filter_summary_by_role(summary_df, user_role, user_name)
        qa_iter_df = filter_iter_df_by_role(qa_iter_df, user_role, user_name)
        dev_iter_df = filter_iter_df_by_role(dev_iter_df, user_role, user_name)
        an_iter_df = filter_iter_df_by_role(an_iter_df, user_role, user_name)

        with content_col:
            if selected_key == "overview":
                render_overview_tab(summary_df, net_day_hours=net_day_hours)

            elif selected_key == "periods":
                render_periods_tab(monthly_sprints_list, quarter_list, full_raw_df, global_summary_df)

            elif selected_key == "estimates":
                render_estimates_tab(
                    summary_df, qa_iter_df, dev_iter_df, an_iter_df, team=team,
                    overall_only=(team.project or imported_names.get(team_id, team.name)) == CREATION_SIZE_PROJECT,
                )

            elif selected_key == "deadlines":
                render_deadlines_tab(summary_df)

            elif selected_key == "types":
                render_types_tab(summary_df)

            elif selected_key == "priorities":
                render_priorities_tab(summary_df)

            elif selected_key == "qa":
                render_role_tab(
                    role_title="QA",
                    queue_events=full_raw_df,
                    queue_team_id=team_id,
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

            elif selected_key == "dev":
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

            elif selected_key == "analytics":
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

            elif selected_key == "detail":
                # Для детализации используем global_summary_df и все задачи (не отфильтрованные по роли)
                render_task_detail_tab(global_summary_df, all_active_tids)


if __name__ == "__main__":
    # Запуск только при прямом вызове python main.py (не при импорте в тестах)
    import streamlit as st
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    
    if get_script_run_ctx() is not None:
        run_streamlit_app()
