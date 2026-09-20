"""ui/tabs/priorities.py — Влияние приоритета на дисциплину очередей."""
import pandas as pd
import plotly.express as px
import streamlit as st
from config import PRIORITY_ORDER
from utils.stats import calc_stats
from ui.components import render_ai_audit_button


def render_priorities_tab(summary_df: pd.DataFrame, gemini_key: str = ""):
    st.subheader("⚡ Влияние приоритета на прохождение очереди и Lead Time")
    st.caption("Проверка дисциплины очередей: насколько быстрее берутся в работу высокоприоритетные задачи")

    prio_df = summary_df.copy()
    if "Приоритет" not in prio_df.columns:
        st.info("Поле приоритетов отсутствует в выборке.")
        return

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
        st.plotly_chart(fig_prio_wait, use_container_width=True, key="chart_priorities_wait_bar")

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
        st.plotly_chart(fig_prio_flow, use_container_width=True, key="chart_priorities_flow_bar")

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
    valid_cols = [c for c in tbl_prio_cols if c in filtered_prio_df.columns]

    st.caption(f"Отображено: **{len(filtered_prio_df)}** из **{len(prio_df)}** задач")
    st.dataframe(filtered_prio_df[valid_cols], use_container_width=True, hide_index=True)

    csv_prio_exp = filtered_prio_df[valid_cols].to_csv(index=False).encode("utf-8-sig")
    st.download_button("📥 Скачать реестр очередей по приоритетам (CSV)", csv_prio_exp, "tasks_by_priority.csv", "text/csv")

    render_ai_audit_button(
        button_label="ИИ-аудит дисциплины очередей и приоритетов",
        key_suffix="priorities",
        agent_role="Kanban Flow Master",
        agent_goal="Проверить соблюдение классов обслуживания (Class of Service) и устранить зависание критических задач в очередях",
        context_prompt=(
            f"Статистика очередей по приоритетам:\n"
            f"{prio_stat_table[['Приоритет', 'Задач (шт)', 'Lead Time Ср (д.)', 'Всего очередей Ср (д.)', 'Flow Efficiency (%)']].to_string(index=False)}"
        ),
        gemini_key=gemini_key
    )