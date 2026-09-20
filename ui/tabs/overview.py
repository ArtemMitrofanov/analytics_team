"""ui/tabs/overview.py — Сквозная воронка поставки и фазы жизненного цикла."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from config import (
    ALL_TRACKED_STATUSES,
    STATUS_ANALYTICS_WAIT,
    STATUS_ANALYTICS_WORK,
    STATUS_ANALYTICS_REVIEW,
    STATUS_DEV_WAIT,
    STATUS_DEV_WORK,
    STATUS_DEV_REVIEW,
    STATUS_QA_WORK,
)
from utils.stats import calc_stats


def render_overview_tab(
    summary_df: pd.DataFrame,
    net_day_hours: float = 7.0
):
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
        phase = (
            "Аналитика"
            if st_name in STATUS_ANALYTICS_WAIT + STATUS_ANALYTICS_WORK + STATUS_ANALYTICS_REVIEW
            else ("Разработка" if st_name in STATUS_DEV_WAIT + STATUS_DEV_WORK + STATUS_DEV_REVIEW else "Тестирование")
        )
        cat = "Работа" if st_name in STATUS_ANALYTICS_WORK + STATUS_DEV_WORK + STATUS_QA_WORK else "Очередь / Ревью"
        status_stats.append({
            "Этап": phase,
            "Тип": cat,
            "Статус": st_name,
            "Среднее (д.)": round(mean_v, 2),
            "Медиана (д.)": round(med_v, 2),
            "P85 (д.)": round(p85_v, 2),
            "Задач с этапом": cnt_v,
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
    st.plotly_chart(fig_phases, use_container_width=True, key="chart_overview_phases")