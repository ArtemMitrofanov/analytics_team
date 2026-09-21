"""data/pipeline.py — Быстрая пакетная обработка и кэширование результатов."""
import pandas as pd
import streamlit as st
from data.task_processor import process_single_task


def _process_all_tasks(
    raw_df: pd.DataFrame,
    work_start_h: int,
    work_end_h: int,
    net_ratio: float,
    net_day_hours: float
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
            str(tid), sub_df, work_start_h, work_end_h, net_ratio, net_day_hours
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


@st.cache_data(show_spinner="Выполняется быстрый анализ журнала задач...")
def process_all_tasks_cached(
    db_fingerprint: str,
    work_start_h: int,
    work_end_h: int,
    net_ratio: float,
    net_day_hours: float
):
    """Обрабатывает все задачи из DuckDB. Кэш ключируется по отпечатку БД, а не по DataFrame."""
    from db import get_all_events

    raw_df = get_all_events()
    if raw_df.empty:
        return (
            pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
            pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
            pd.DataFrame(),
        )
    return _process_all_tasks(raw_df, work_start_h, work_end_h, net_ratio, net_day_hours)


def process_all_tasks(
    raw_df: pd.DataFrame,
    work_start_h: int,
    work_end_h: int,
    net_ratio: float,
    net_day_hours: float
):
    """Некэшированная обработка переданного DataFrame (используется в тестах)."""
    return _process_all_tasks(raw_df, work_start_h, work_end_h, net_ratio, net_day_hours)
