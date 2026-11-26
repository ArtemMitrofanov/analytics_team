"""ui/tabs/task_detail.py — Индивидуальная аналитика конкретной задачи."""
from typing import Sequence
import pandas as pd
import plotly.express as px
import streamlit as st
from config import ALL_TRACKED_STATUSES
from data.workflow import FINANCE_EXTRA_STATUSES, FINANCE_PROJECT, READY_AT, RELEASED_AT, RELEASE_WAIT
from ui.bento import render_plotly


def render_task_detail_tab(summary_df: pd.DataFrame, unique_tasks: Sequence[str]):
    if not list(unique_tasks):
        st.info("Нет доступных задач для детализации.")
        return

    selected_task = st.selectbox("Выберите задачу для детализации:", unique_tasks)
    sub = summary_df[summary_df["Задача"] == selected_task]
    if sub.empty:
        st.warning("Информация по задаче не найдена.")
        return

    task_info = sub.iloc[0]

    is_finance = str(selected_task).rpartition("-")[0] == FINANCE_PROJECT

    def fmt(column, unit=" д."):
        value = task_info.get(column)
        return "—" if pd.isna(value) else f"{value}{unit}"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Lead Time до «К релизу»" if is_finance else "Полный Lead Time", fmt("Полный Lead Time (д.)"))
    c2.metric("Всего очередей", fmt("Всего очередей (д.)"), delta_color="inverse")
    c3.metric("Чистая работа", fmt("Чистая работа (д.)"))
    c4.metric("Flow Efficiency", fmt("Сквозной Flow Efficiency (%)", "%"))

    if is_finance:
        ready_col, released_col, wait_col = st.columns(3)
        ready_col.metric("Готово к релизу", fmt(READY_AT, ""))
        released_col.metric("Зарелизили", fmt(RELEASED_AT, ""))
        wait_col.metric("Ожидание релиза", fmt(RELEASE_WAIT))

    statuses = [*ALL_TRACKED_STATUSES, *FINANCE_EXTRA_STATUSES] if is_finance else ALL_TRACKED_STATUSES
    recorded = [
        (status, value) for status in statuses
        if pd.notna(value := task_info.get(f"{status} (д.)")) and value > 0
    ]

    if recorded:
        fig_task_pie = px.pie(
            names=[status for status, _ in recorded],
            values=[value for _, value in recorded],
            title=f"Структура времени задачи {selected_task} ({task_info.get('Тип задачи', '')} | {task_info.get('Приоритет', '')}) по статусам",
            hole=0.45,
        )
        fig_task_pie.update_layout(height=350)
        render_plotly(fig_task_pie, key=f"chart_task_pie_{selected_task}")
