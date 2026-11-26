"""data/pipeline.py — Быстрая пакетная обработка и кэширование результатов."""
from hashlib import sha256
from pathlib import Path
from time import perf_counter

import pandas as pd
import streamlit as st
from config import CORE_QA_TEAM, DEFAULT_TEAM_ID
from data.task_processor import process_single_task


def _pipeline_version() -> str:
    root = Path(__file__).resolve().parents[1]
    digest = sha256(pd.__version__.encode())
    for name in ("data/pipeline.py", "data/task_processor.py", "data/workflow.py", "utils/time_calc.py",
                 "config.py", "config/team.json", "db.py"):
        path = root / name
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


PIPELINE_VERSION = _pipeline_version()


def _process_all_tasks(
    raw_df: pd.DataFrame,
    work_start_h: int,
    work_end_h: int,
    net_ratio: float,
    net_day_hours: float,
    *,
    core_qa: tuple[str, ...] = tuple(CORE_QA_TEAM),
):
    """Группирует датафрейм один раз и обрабатывает задачи за один проход без повторного сканирования."""
    if "task_identifier" not in raw_df.columns:
        raw_df = raw_df.copy()
        raw_df["task_identifier"] = raw_df["task_id"]

    tasks_summaries = []
    qa_iterations, dev_iterations, an_iterations = [], [], []
    qa_wait_intervals = []
    dev_reviews, an_reviews, qa_reworks = [], [], []

    # O(N) вместо O(N^2)
    grouped = raw_df.groupby("task_identifier", sort=False)
    for tid, sub_df in grouped:
        (
            s_data,
            qa_iters,
            dev_iters,
            an_iters,
            dev_revs,
            an_revs,
            reworks,
            qa_wait_iters,
        ) = process_single_task(
            str(tid), sub_df, work_start_h, work_end_h, net_ratio, net_day_hours, core_qa=core_qa
        )
        tasks_summaries.append(s_data)
        qa_iterations.extend(qa_iters)
        dev_iterations.extend(dev_iters)
        an_iterations.extend(an_iters)
        dev_reviews.extend(dev_revs)
        an_reviews.extend(an_revs)
        qa_reworks.extend(reworks)
        qa_wait_intervals.extend(qa_wait_iters)

    return (
        pd.DataFrame(tasks_summaries),
        pd.DataFrame(qa_iterations),
        pd.DataFrame(dev_iterations),
        pd.DataFrame(an_iterations),
        pd.DataFrame(dev_reviews),
        pd.DataFrame(an_reviews),
        pd.DataFrame(qa_reworks),
        pd.DataFrame(qa_wait_intervals),
    )


@st.cache_data(persist="disk", max_entries=8, show_spinner="Выполняется быстрый анализ журнала задач...")
def process_all_tasks_cached(
    db_fingerprint: str,
    work_start_h: int,
    work_end_h: int,
    net_ratio: float,
    net_day_hours: float,
    *,
    pipeline_version: str,
    database_key: str,
    team_id: str = DEFAULT_TEAM_ID,
    core_qa: tuple[str, ...] = tuple(CORE_QA_TEAM),
    _timings: dict[str, float] | None = None,
):
    """Кэширует расчёт по версии кода, базе, отпечатку данных и рабочим часам."""
    from db import get_all_events

    # Streamlit excludes underscore-prefixed arguments from the cache key.
    # These timings are populated only when the cached function runs.
    events_started = perf_counter()
    raw_df = get_all_events(team_id=team_id)
    if _timings is not None:
        _timings["pipeline_events"] = perf_counter() - events_started
    if raw_df.empty:
        return (
            pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
            pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
            pd.DataFrame(),
        )
    compute_started = perf_counter()
    result = _process_all_tasks(
        raw_df, work_start_h, work_end_h, net_ratio, net_day_hours, core_qa=core_qa
    )
    if _timings is not None:
        _timings["pipeline_compute"] = perf_counter() - compute_started
    return result


def process_all_tasks(
    raw_df: pd.DataFrame,
    work_start_h: int,
    work_end_h: int,
    net_ratio: float,
    net_day_hours: float
):
    """Некэшированная обработка переданного DataFrame (используется в тестах)."""
    return _process_all_tasks(raw_df, work_start_h, work_end_h, net_ratio, net_day_hours)
