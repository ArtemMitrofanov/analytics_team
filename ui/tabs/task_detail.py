"""ui/tabs/task_detail.py — Индивидуальная аналитика конкретной задачи."""
from typing import Sequence
import pandas as pd
import plotly.express as px
import streamlit as st
from config import ALL_TRACKED_STATUSES
from ui.components import render_ai_audit_button


def render_task_detail_tab(summary_df: pd.DataFrame, unique_tasks: Sequence[str], gemini_key: str = ""):
    if not list(unique_tasks):
        st.info("Нет доступных задач для детализации.")
        return

    selected_task = st.selectbox("Выберите задачу для детализации:", unique_tasks)
    sub = summary_df[summary_df["Задача"] == selected_task]
    if sub.empty:
        st.warning("Информация по задаче не найдена.")
        return

    task_info = sub.iloc[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Полный Lead Time", f"{task_info.get('Полный Lead Time (д.)', 0)} д.")
    c2.metric("Всего очередей", f"{task_info.get('Всего очередей (д.)', 0)} д.", delta_color="inverse")
    c3.metric("Чистая работа", f"{task_info.get('Чистая работа (д.)', 0)} д.")
    c4.metric("Flow Efficiency", f"{task_info.get('Сквозной Flow Efficiency (%)', 0)}%")

    task_status_values = [task_info.get(f"{st_name} (д.)", 0) for st_name in ALL_TRACKED_STATUSES if task_info.get(f"{st_name} (д.)", 0) > 0]
    task_status_labels = [st_name for st_name in ALL_TRACKED_STATUSES if task_info.get(f"{st_name} (д.)", 0) > 0]

    if task_status_values:
        fig_task_pie = px.pie(
            names=task_status_labels,
            values=task_status_values,
            title=f"Структура времени задачи {selected_task} ({task_info.get('Тип задачи', '')} | {task_info.get('Приоритет', '')}) по статусам",
            hole=0.45,
        )
        fig_task_pie.update_layout(height=350)
        st.plotly_chart(fig_task_pie, use_container_width=True, key=f"chart_task_pie_{selected_task}")

    status_breakdown = ", ".join([f"{lbl}: {val}д" for lbl, val in zip(task_status_labels, task_status_values)])
    render_ai_audit_button(
        button_label=f"ИИ-разбор задачи {selected_task}",
        key_suffix=f"task_{selected_task}",
        agent_role="Root Cause Investigator",
        agent_goal="Найти первопричину задержки конкретной задачи и указать на самый узкий этап",
        context_prompt=(
            f"Досье задачи {selected_task}:\n"
            f"- Тип: {task_info.get('Тип задачи', 'Не указан')}, Приоритет: {task_info.get('Приоритет', 'Не указан')}\n"
            f"- Полный Lead Time: {task_info.get('Полный Lead Time (д.)', 0)} д., Очереди: {task_info.get('Всего очередей (д.)', 0)} д., Чистая работа: {task_info.get('Чистая работа (д.)', 0)} д.\n"
            f"- Flow Efficiency: {task_info.get('Сквозной Flow Efficiency (%)', 0)}%\n"
            f"- Распределение по статусам: {status_breakdown}"
        ),
        gemini_key=gemini_key
    )