"""data/pipeline.py — Быстрая пакетная обработка и кэширование результатов."""
import pandas as pd
import streamlit as st
from data.task_processor import process_single_task

@st.cache_data(show_spinner="Выполняется быстрый анализ журнала задач...")
def process_all_tasks_cached(
    raw_df: pd.DataFrame,
    work_start_h: int,
    work_end_h: int,
    net_ratio: float,
    net_day_hours: float
):
    """Группирует датафрейм один раз и обрабатывает задачи за один проход без повторного сканирования."""
    tasks_summaries = []
    qa_iterations, dev_iterations, an_iterations = [], [], []
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

    return (
        pd.DataFrame(tasks_summaries),
        pd.DataFrame(qa_iterations),
        pd.DataFrame(dev_iterations),
        pd.DataFrame(an_iterations),
        pd.DataFrame(dev_reviews),
        pd.DataFrame(an_reviews),
        pd.DataFrame(qa_reworks),
    )