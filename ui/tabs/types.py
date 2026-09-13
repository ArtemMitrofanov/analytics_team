"""ui/tabs/types.py — Анализ структуры потока: Дефекты (Bugs) vs Фичи (Tasks)."""
import pandas as pd
import plotly.express as px
import streamlit as st
from utils.stats import calc_stats
from ui.components import render_ai_audit_button


def render_types_tab(summary_df: pd.DataFrame, gemini_key: str = ""):
    st.subheader("🐞 Анализ структуры потока: Дефекты (Bugs) vs Фичи / Задачи (Tasks)")
    st.caption("Оценка баланса создания новой ценности (Value Demand) и устранения дефектов (Failure Demand)")

    types_df = summary_df.copy()
    if "Тип задачи" not in types_df.columns:
        st.info("Типы задач не определены в текущем наборе данных.")
        return

    bugs_df = types_df[types_df["Тип задачи"] == "Дефект (Bug)"]
    features_df = types_df[types_df["Тип задачи"].isin(["Фича / Задача (Task)", "Эпик (Epic)"])]

    total_cnt = len(types_df)
    bug_cnt = len(bugs_df)
    feat_cnt = len(features_df)

    bug_pct = (bug_cnt / total_cnt * 100) if total_cnt > 0 else 0.0
    feat_pct = (feat_cnt / total_cnt * 100) if total_cnt > 0 else 0.0

    bug_lt_m, bug_lt_med, bug_lt_p85, _ = calc_stats(bugs_df.get("Полный Lead Time (д.)", pd.Series(dtype=float)))
    feat_lt_m, feat_lt_med, feat_lt_p85, _ = calc_stats(features_df.get("Полный Lead Time (д.)", pd.Series(dtype=float)))

    t_c1, t_c2, t_c3, t_c4 = st.columns(4)
    t_c1.metric("Доля дефектов (Failure Demand)", f"{bug_pct:.1f}%", f"{bug_cnt} багов", delta_color="inverse")
    t_c2.metric("Доля фичей (Value Demand)", f"{feat_pct:.1f}%", f"{feat_cnt} задач/эпиков")
    t_c3.metric("Lead Time Дефектов (Ср / P85)", f"{bug_lt_m:.1f} д.", f"P85: {bug_lt_p85:.1f} д.")
    t_c4.metric("Lead Time Фичей (Ср / P85)", f"{feat_lt_m:.1f} д.", f"P85: {feat_lt_p85:.1f} д.")

    st.markdown("---")
    t_col_g1, t_col_g2 = st.columns(2)

    with t_col_g1:
        fig_type_pie = px.pie(
            types_df,
            names="Тип задачи",
            title="Структура потока задач в периоде (Flow Distribution)",
            hole=0.45,
            color="Тип задачи",
            color_discrete_map={
                "Дефект (Bug)": "#d62728",
                "Фича / Задача (Task)": "#1f77b4",
                "Эпик (Epic)": "#9467bd",
                "Эксплуатация (Run)": "#ff7f0e",
                "Техдолг": "#7f7f7f",
                "Не определен": "#c7c7c7",
            }
        )
        fig_type_pie.update_layout(height=340)
        st.plotly_chart(fig_type_pie, use_container_width=True, key="chart_types_pie")

    with t_col_g2:
        compare_phases_data = []
        for group_name, g_df in [("Дефекты (Bugs)", bugs_df), ("Фичи (Tasks/Epics)", features_df)]:
            if not g_df.empty:
                compare_phases_data.append({
                    "Категория": group_name,
                    "В аналитике (д.)": g_df.get("В аналитике (д.)", pd.Series([0])).mean(),
                    "В разработке (д.)": g_df.get("В разработке (д.)", pd.Series([0])).mean(),
                    "В тестировании (дни)": g_df.get("В тестировании (дни)", pd.Series([0])).mean(),
                    "Очереди и ревью (д.)": g_df.get("Всего очередей (д.)", pd.Series([0])).mean(),
                })
        if compare_phases_data:
            fig_comp_bar = px.bar(
                pd.DataFrame(compare_phases_data),
                x="Категория",
                y=["В аналитике (д.)", "В разработке (д.)", "В тестировании (дни)", "Очереди и ревью (д.)"],
                barmode="group",
                title="Среднее время фаз: Баги vs Фичи (в днях)",
                text_auto=".2f",
                color_discrete_sequence=["#aec7e8", "#1f77b4", "#2ca02c", "#d62728"]
            )
            fig_comp_bar.update_layout(height=340, yaxis_title="Рабочие дни (д.)")
            st.plotly_chart(fig_comp_bar, use_container_width=True, key="chart_types_comp_bar")

    st.markdown("---")
    st.markdown("#### 📋 Сводная таблица по типам задач")

    col_t_flt, col_t_srch = st.columns([1, 1])
    with col_t_flt:
        sel_types_filter = st.multiselect(
            "Фильтр по типу задачи:",
            options=types_df["Тип задачи"].unique(),
            default=types_df["Тип задачи"].unique()
        )
    with col_t_srch:
        search_type_q = st.text_input("🔍 Быстрый поиск задачи по номеру:", placeholder="Например: 2421", key="search_type_tbl")

    filtered_types_df = types_df.copy()
    if sel_types_filter:
        filtered_types_df = filtered_types_df[filtered_types_df["Тип задачи"].isin(sel_types_filter)]
    if search_type_q.strip():
        filtered_types_df = filtered_types_df[filtered_types_df["Задача"].astype(str).str.contains(search_type_q.strip(), case=False, na=False)]

    tbl_type_cols = [
        "Задача", "Тип задачи", "task_size",
        "В аналитике (д.)", "В разработке (д.)", "В тестировании (дни)",
        "Всего очередей (д.)", "Полный Lead Time (д.)", "Сквозной Flow Efficiency (%)"
    ]
    valid_cols = [c for c in tbl_type_cols if c in filtered_types_df.columns]

    st.caption(f"Отображено задач: **{len(filtered_types_df)}** из **{total_cnt}**")
    st.dataframe(filtered_types_df[valid_cols], use_container_width=True, hide_index=True)

    csv_types_exp = filtered_types_df[valid_cols].to_csv(index=False).encode("utf-8-sig")
    st.download_button("📥 Скачать реестр по типам задач (CSV)", csv_types_exp, "tasks_by_type.csv", "text/csv")

    render_ai_audit_button(
        button_label="ИИ-аудит баланса дефектов и фичей",
        key_suffix="types",
        agent_role="Product Quality & Flow Strategist",
        agent_goal="Снизить долю Failure Demand (багов) и освободить ресурс команды под разработку фичей (Value Demand)",
        context_prompt=(
            f"Структура потока работ команды:\n"
            f"- Доля багов (Failure Demand): {bug_pct:.1f}% ({bug_cnt} шт), Lead Time ср = {bug_lt_m:.1f} д. (P85 = {bug_lt_p85:.1f} д.)\n"
            f"- Доля фичей (Value Demand): {feat_pct:.1f}% ({feat_cnt} шт), Lead Time ср = {feat_lt_m:.1f} д. (P85 = {feat_lt_p85:.1f} д.)"
        ),
        gemini_key=gemini_key
    )