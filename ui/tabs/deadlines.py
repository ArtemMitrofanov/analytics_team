"""ui/tabs/deadlines.py — Контроль выполнения обязательств и дедлайнов (SLA)."""
import pandas as pd
import plotly.express as px
import streamlit as st
from ui.components import render_ai_audit_button


def render_deadlines_tab(summary_df: pd.DataFrame, gemini_key: str = ""):
    st.subheader("⏰ Контроль выполнения обязательств и дедлайнов (SLA)")
    st.caption("Анализ соблюдения сроков заказчика, частоты переносов дедлайнов (Slippage) и просрочек")

    if "has_deadline" not in summary_df.columns:
        st.info("Поле дедлайнов не найдено в структуре данных.")
        return

    deadlines_df = summary_df[summary_df["has_deadline"] == True].copy()

    if not deadlines_df.empty:
        total_with_dl = len(deadlines_df)
        on_time_tasks = deadlines_df[deadlines_df["sla_status"] == "В срок (On-Time)"]
        overdue_tasks = deadlines_df[deadlines_df["sla_status"].isin(["С опозданием (Overdue)", "В работе (просрочено)"])]
        shifted_tasks = deadlines_df[deadlines_df.get("deadline_shifts", 0) > 0]

        on_time_pct = (len(on_time_tasks) / total_with_dl * 100) if total_with_dl > 0 else 0.0
        overdue_pct = (len(overdue_tasks) / total_with_dl * 100) if total_with_dl > 0 else 0.0
        shifted_pct = (len(shifted_tasks) / total_with_dl * 100) if total_with_dl > 0 else 0.0

        avg_slippage = shifted_tasks["deadline_slippage_days"].mean() if not shifted_tasks.empty else 0.0
        max_slippage = shifted_tasks["deadline_slippage_days"].max() if not shifted_tasks.empty else 0.0

        dl1, dl2, dl3, dl4 = st.columns(4)
        dl1.metric("Сдано в срок (On-Time Rate)", f"{on_time_pct:.1f}%", f"{len(on_time_tasks)} из {total_with_dl} задач")
        dl2.metric("Просрочено (Overdue)", f"{overdue_pct:.1f}%", f"{len(overdue_tasks)} задач", delta_color="inverse")
        dl3.metric("Задач с переносом срока", f"{shifted_pct:.1f}%", f"{len(shifted_tasks)} тикетов", delta_color="inverse")
        dl4.metric("Средний сдвиг дедлайна", f"{avg_slippage:.1f} д.", f"Макс: {max_slippage} д.")

        st.markdown("---")
        c_dl_pie, c_dl_bar = st.columns(2)

        with c_dl_pie:
            fig_sla_pie = px.pie(
                deadlines_df,
                names="sla_status",
                title="Распределение задач по статусу дедлайна",
                hole=0.45,
                color="sla_status",
                color_discrete_map={
                    "В срок (On-Time)": "#2ca02c",
                    "В работе (в графике)": "#1f77b4",
                    "С опозданием (Overdue)": "#d62728",
                    "В работе (просрочено)": "#ff7f0e",
                }
            )
            fig_sla_pie.update_layout(height=340)
            st.plotly_chart(fig_sla_pie, use_container_width=True, key="chart_deadlines_sla_pie")

        with c_dl_bar:
            if not shifted_tasks.empty:
                fig_slip_hist = px.histogram(
                    shifted_tasks,
                    x="deadline_slippage_days",
                    nbins=15,
                    title="Распределение величины переноса дедлайнов (в днях)",
                    color_discrete_sequence=["#ff7f0e"]
                )
                fig_slip_hist.update_layout(height=340, xaxis_title="Сдвиг дедлайна (календарных дней)", yaxis_title="Количество задач")
                st.plotly_chart(fig_slip_hist, use_container_width=True, key="chart_deadlines_slip_hist")
            else:
                st.info("В выборке нет задач с переносами дедлайнов.")

        st.markdown("---")
        st.markdown("#### 📋 Реестр задач с дедлайнами заказчика")

        col_flt_sla, col_srch_dl = st.columns([1, 1])
        with col_flt_sla:
            sla_filter_opts = st.multiselect(
                "Фильтр по статусу SLA:",
                options=deadlines_df["sla_status"].unique(),
                default=deadlines_df["sla_status"].unique()
            )
        with col_srch_dl:
            srch_dl_q = st.text_input("🔍 Поиск задачи по номеру:", placeholder="Например: 2421", key="search_dl_tbl")

        display_dl_df = deadlines_df.copy()
        if sla_filter_opts:
            display_dl_df = display_dl_df[display_dl_df["sla_status"].isin(sla_filter_opts)]
        if srch_dl_q.strip():
            display_dl_df = display_dl_df[display_dl_df["Задача"].astype(str).str.contains(srch_dl_q.strip(), case=False, na=False)]

        display_dl_df["Первый дедлайн"] = pd.to_datetime(display_dl_df["first_deadline"]).dt.strftime("%d.%m.%Y")
        display_dl_df["Финальный дедлайн"] = pd.to_datetime(display_dl_df["final_deadline"]).dt.strftime("%d.%m.%Y")
        display_dl_df["Дата завершения"] = display_dl_df["finished_at"].apply(
            lambda d: pd.to_datetime(d).strftime("%d.%m.%Y %H:%M") if pd.notna(d) else "В процессе"
        )

        display_dl_df = display_dl_df.rename(columns={
            "task_size": "Размер",
            "deadline_shifts": "Переносов (раз)",
            "deadline_slippage_days": "Сдвиг (дней)",
            "sla_status": "Статус SLA",
            "delay_days": "Отклонение (дней)"
        })

        rename_dl_cols = [
            "Задача", "Размер", "Первый дедлайн", "Финальный дедлайн",
            "Переносов (раз)", "Сдвиг (дней)", "Дата завершения",
            "Статус SLA", "Отклонение (дней)", "Полный Lead Time (д.)"
        ]
        valid_cols = [c for c in rename_dl_cols if c in display_dl_df.columns]

        st.caption(f"Отображено: **{len(display_dl_df)}** из **{total_with_dl}** задач с установленным дедлайном")
        st.dataframe(display_dl_df[valid_cols], use_container_width=True, hide_index=True)

        csv_dl_exp = display_dl_df[valid_cols].to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 Скачать реестр дедлайнов (CSV)", csv_dl_exp, "task_deadlines_sla.csv", "text/csv")

        render_ai_audit_button(
            button_label="ИИ-аудит выполнения дедлайнов (SLA)",
            key_suffix="deadlines",
            agent_role="SLA & Release Commitment Manager",
            agent_goal="Оценить причины систематических переносов сроков и предложить механизм защиты дедлайнов",
            context_prompt=(
                f"Метрики выполнения дедлайнов заказчика:\n"
                f"- Задач с дедлайном: {total_with_dl}\n"
                f"- On-Time Delivery: {on_time_pct:.1f}%\n"
                f"- Просрочено: {overdue_pct:.1f}%\n"
                f"- Задач с переносами дедлайна: {shifted_pct:.1f}%\n"
                f"- Средний перенос: {avg_slippage:.1f} д. (макс: {max_slippage} д.)"
            ),
            gemini_key=gemini_key
        )
    else:
        st.info("В выбранном периоде нет задач с заполненным полем «Дедлайн заказчика».")