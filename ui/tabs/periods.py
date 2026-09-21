<<<<<<< HEAD
"""ui/tabs/periods.py — Динамика метрик по месяцам и кварталам (по дате завершения задачи)."""
=======
"""ui/tabs/periods.py — Сравнительный анализ по спринтам и кварталам."""
>>>>>>> c7b0efa56c7e205b1b045fcc5a20a4380bdd34e3
from typing import List, Dict, Any
import pandas as pd
import plotly.express as px
import streamlit as st
from utils.stats import calc_stats

<<<<<<< HEAD

=======
>>>>>>> c7b0efa56c7e205b1b045fcc5a20a4380bdd34e3
def render_periods_tab(
    monthly_sprints_list: List[Dict[str, Any]],
    quarter_list: List[Dict[str, Any]],
    full_raw_df: pd.DataFrame,
    global_summary_df: pd.DataFrame
):
<<<<<<< HEAD
    st.subheader("📅 Динамика по периодам")
    st.caption("Задачи атрибутируются в период, в котором они были завершены (статусы: Протестировано / К релизу / Завершено). Задачи без завершения попадают в «В работе».")

    compare_scale = st.radio(
        "Группировка:",
        options=["По месяцам", "По кварталам"],
        horizontal=True
    )

    active_compare_list = monthly_sprints_list if compare_scale == "По месяцам" else quarter_list

    if "finished_at" in global_summary_df.columns:
        finished_dt = pd.to_datetime(global_summary_df["finished_at"], errors="coerce")
    else:
        finished_dt = pd.Series(pd.NaT, index=global_summary_df.index)

    compare_rows = []
    for p_item in active_compare_list:
        start_d = pd.Timestamp(p_item["start_date"])
        end_d = pd.Timestamp(p_item["end_date"]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        in_period = finished_dt.between(start_d, end_d)
        sp_df = global_summary_df[in_period]
=======
    st.subheader("📅 Сравнительный анализ периодов поставки")
    st.caption("Динамика сквозной воронки поставки и ключевых метрик по каждой роли")

    compare_scale = st.radio(
        "Масштаб сравнения:",
        options=["По месячным спринтам", "По кварталам"],
        horizontal=True
    )

    active_compare_list = monthly_sprints_list if compare_scale == "По месячным спринтам" else quarter_list

    compare_rows = []
    for p_item in active_compare_list:
        sp_sub = full_raw_df[
            (full_raw_df["timestamp"].dt.date >= p_item["start_date"])
            & (full_raw_df["timestamp"].dt.date <= p_item["end_date"])
            & (full_raw_df["changed_value"].isin(["Текущий статус", "State"]))
        ]
        sp_task_ids = sp_sub["task_identifier"].dropna().unique()
        sp_df = global_summary_df[global_summary_df["Задача"].isin(sp_task_ids)]
>>>>>>> c7b0efa56c7e205b1b045fcc5a20a4380bdd34e3

        if not sp_df.empty:
            lt_m, lt_med, lt_p85, _ = calc_stats(sp_df.get("Полный Lead Time (д.)", pd.Series(dtype=float)))
            wt_m, wt_med, wt_p85, _ = calc_stats(sp_df.get("Всего очередей (д.)", pd.Series(dtype=float)))
            wk_m, wk_med, wk_p85, _ = calc_stats(sp_df.get("Чистая работа (д.)", pd.Series(dtype=float)))
            fl_m, fl_med, _, _ = calc_stats(sp_df.get("Сквозной Flow Efficiency (%)", pd.Series(dtype=float)))

<<<<<<< HEAD
            qa_act = sp_df[sp_df.get("В тестировании (дни)", pd.Series(0, index=sp_df.index)) > 0]
=======
            qa_act = sp_df[sp_df.get("В тестировании (дни)", 0) > 0]
>>>>>>> c7b0efa56c7e205b1b045fcc5a20a4380bdd34e3
            qa_w_m, qa_w_med, qa_w_p85, _ = calc_stats(qa_act.get("В тестировании (дни)", pd.Series(dtype=float)))
            qa_q_m, qa_q_med, qa_q_p85, _ = calc_stats(qa_act.get("Очередь ожидания QA (дни)", pd.Series(dtype=float)))
            qa_c_m, qa_c_med, qa_c_p85, _ = calc_stats(qa_act.get("Циклтайм QA (дни)", pd.Series(dtype=float)))
            qa_fl_m, _, _, _ = calc_stats(qa_act.get("Flow Efficiency QA (%)", pd.Series(dtype=float)))

<<<<<<< HEAD
            dev_act = sp_df[sp_df.get("В разработке (д.)", pd.Series(0, index=sp_df.index)) > 0]
=======
            dev_act = sp_df[sp_df.get("В разработке (д.)", 0) > 0]
>>>>>>> c7b0efa56c7e205b1b045fcc5a20a4380bdd34e3
            dev_w_m, dev_w_med, dev_w_p85, _ = calc_stats(dev_act.get("В разработке (д.)", pd.Series(dtype=float)))
            dev_q_m, dev_q_med, dev_q_p85, _ = calc_stats(dev_act.get("Очередь/Код Ревью Dev (д.)", pd.Series(dtype=float)))
            dev_c_m, dev_c_med, dev_c_p85, _ = calc_stats(dev_act.get("Цикл Разработки (д.)", pd.Series(dtype=float)))
            dev_fl_m, _, _, _ = calc_stats(dev_act.get("Flow Разработки (%)", pd.Series(dtype=float)))

<<<<<<< HEAD
            an_act = sp_df[sp_df.get("В аналитике (д.)", pd.Series(0, index=sp_df.index)) > 0]
=======
            an_act = sp_df[sp_df.get("В аналитике (д.)", 0) > 0]
>>>>>>> c7b0efa56c7e205b1b045fcc5a20a4380bdd34e3
            an_w_m, an_w_med, an_w_p85, _ = calc_stats(an_act.get("В аналитике (д.)", pd.Series(dtype=float)))
            an_q_m, an_q_med, an_q_p85, _ = calc_stats(an_act.get("Очередь/Ревью Аналитики (д.)", pd.Series(dtype=float)))
            an_c_m, an_c_med, an_c_p85, _ = calc_stats(an_act.get("Цикл Аналитики (д.)", pd.Series(dtype=float)))
            an_fl_m, _, _, _ = calc_stats(an_act.get("Flow Аналитики (%)", pd.Series(dtype=float)))

            compare_rows.append({
                "Период": p_item["period_name"],
<<<<<<< HEAD
                "Задач завершено (шт)": len(sp_df),
=======
                "Задач (шт)": len(sp_task_ids),
>>>>>>> c7b0efa56c7e205b1b045fcc5a20a4380bdd34e3
                "Lead Time Ср (д.)": round(lt_m, 2),
                "Lead Time Мед (д.)": round(lt_med, 2),
                "Lead Time P85 (д.)": round(lt_p85, 2),
                "Очереди Ср (д.)": round(wt_m, 2),
                "Чистая работа Ср (д.)": round(wk_m, 2),
                "Сквозной Flow (%)": round(fl_m, 1),
                "QA В тестировании Ср (д.)": round(qa_w_m, 2),
                "QA Очередь Ср (д.)": round(qa_q_m, 2),
                "QA Циклтайм Ср (д.)": round(qa_c_m, 2),
                "QA Flow (%)": round(qa_fl_m, 1),
                "Dev В разработке Ср (д.)": round(dev_w_m, 2),
                "Dev Очередь/Ревью Ср (д.)": round(dev_q_m, 2),
                "Dev Цикл Ср (д.)": round(dev_c_m, 2),
                "Dev Flow (%)": round(dev_fl_m, 1),
                "An В аналитике Ср (д.)": round(an_w_m, 2),
                "An Очередь/Ревью Ср (д.)": round(an_q_m, 2),
                "An Цикл Ср (д.)": round(an_c_m, 2),
                "An Flow (%)": round(an_fl_m, 1),
            })

<<<<<<< HEAD
    # Незавершённые задачи — отдельной строкой, чтобы не терять из виду
    not_finished = global_summary_df[finished_dt.isna()]
    if not not_finished.empty:
        lt_m, lt_med, lt_p85, _ = calc_stats(not_finished.get("Полный Lead Time (д.)", pd.Series(dtype=float)))
        wt_m, _, _, _ = calc_stats(not_finished.get("Всего очередей (д.)", pd.Series(dtype=float)))
        wk_m, _, _, _ = calc_stats(not_finished.get("Чистая работа (д.)", pd.Series(dtype=float)))
        fl_m, _, _, _ = calc_stats(not_finished.get("Сквозной Flow Efficiency (%)", pd.Series(dtype=float)))
        qa_act = not_finished[not_finished.get("В тестировании (дни)", pd.Series(0, index=not_finished.index)) > 0]
        dev_act = not_finished[not_finished.get("В разработке (д.)", pd.Series(0, index=not_finished.index)) > 0]
        an_act = not_finished[not_finished.get("В аналитике (д.)", pd.Series(0, index=not_finished.index)) > 0]
        qa_w_m, _, _, _ = calc_stats(qa_act.get("В тестировании (дни)", pd.Series(dtype=float)))
        qa_q_m, _, _, _ = calc_stats(qa_act.get("Очередь ожидания QA (дни)", pd.Series(dtype=float)))
        qa_c_m, _, _, _ = calc_stats(qa_act.get("Циклтайм QA (дни)", pd.Series(dtype=float)))
        qa_fl_m, _, _, _ = calc_stats(qa_act.get("Flow Efficiency QA (%)", pd.Series(dtype=float)))
        dev_w_m, _, _, _ = calc_stats(dev_act.get("В разработке (д.)", pd.Series(dtype=float)))
        dev_q_m, _, _, _ = calc_stats(dev_act.get("Очередь/Код Ревью Dev (д.)", pd.Series(dtype=float)))
        dev_c_m, _, _, _ = calc_stats(dev_act.get("Цикл Разработки (д.)", pd.Series(dtype=float)))
        dev_fl_m, _, _, _ = calc_stats(dev_act.get("Flow Разработки (%)", pd.Series(dtype=float)))
        an_w_m, _, _, _ = calc_stats(an_act.get("В аналитике (д.)", pd.Series(dtype=float)))
        an_q_m, _, _, _ = calc_stats(an_act.get("Очередь/Ревью Аналитики (д.)", pd.Series(dtype=float)))
        an_c_m, _, _, _ = calc_stats(an_act.get("Цикл Аналитики (д.)", pd.Series(dtype=float)))
        an_fl_m, _, _, _ = calc_stats(an_act.get("Flow Аналитики (%)", pd.Series(dtype=float)))
        compare_rows.append({
            "Период": "⏳ В работе (не завершено)",
            "Задач завершено (шт)": len(not_finished),
            "Lead Time Ср (д.)": round(lt_m, 2),
            "Lead Time Мед (д.)": round(lt_med, 2),
            "Lead Time P85 (д.)": round(lt_p85, 2),
            "Очереди Ср (д.)": round(wt_m, 2),
            "Чистая работа Ср (д.)": round(wk_m, 2),
            "Сквозной Flow (%)": round(fl_m, 1),
            "QA В тестировании Ср (д.)": round(qa_w_m, 2),
            "QA Очередь Ср (д.)": round(qa_q_m, 2),
            "QA Циклтайм Ср (д.)": round(qa_c_m, 2),
            "QA Flow (%)": round(qa_fl_m, 1),
            "Dev В разработке Ср (д.)": round(dev_w_m, 2),
            "Dev Очередь/Ревью Ср (д.)": round(dev_q_m, 2),
            "Dev Цикл Ср (д.)": round(dev_c_m, 2),
            "Dev Flow (%)": round(dev_fl_m, 1),
            "An В аналитике Ср (д.)": round(an_w_m, 2),
            "An Очередь/Ревью Ср (д.)": round(an_q_m, 2),
            "An Цикл Ср (д.)": round(an_c_m, 2),
            "An Flow (%)": round(an_fl_m, 1),
        })

=======
>>>>>>> c7b0efa56c7e205b1b045fcc5a20a4380bdd34e3
    cmp_df = pd.DataFrame(compare_rows)

    if not cmp_df.empty:
        st.markdown("#### 1. Сквозная воронка поставки по периодам")
        overview_cols = [
<<<<<<< HEAD
            "Период", "Задач завершено (шт)",
=======
            "Период", "Задач (шт)",
>>>>>>> c7b0efa56c7e205b1b045fcc5a20a4380bdd34e3
            "Lead Time Ср (д.)", "Lead Time Мед (д.)", "Lead Time P85 (д.)",
            "Очереди Ср (д.)", "Чистая работа Ср (д.)", "Сквозной Flow (%)"
        ]
        st.dataframe(cmp_df[overview_cols], use_container_width=True, hide_index=True)

        c_g1, c_g2 = st.columns(2)
        with c_g1:
            fig_lt = px.bar(
                cmp_df,
                x="Период",
                y=["Lead Time Ср (д.)", "Lead Time Мед (д.)", "Lead Time P85 (д.)"],
                barmode="group",
<<<<<<< HEAD
                title="Сквозной Lead Time завершённых задач (Среднее / Медиана / P85)",
=======
                title="Сквозной Lead Time (Среднее / Медиана / P85)",
>>>>>>> c7b0efa56c7e205b1b045fcc5a20a4380bdd34e3
                text_auto=".2f",
                color_discrete_sequence=["#1f77b4", "#aec7e8", "#ff7f0e"]
            )
            fig_lt.update_layout(height=360, yaxis_title="Рабочие дни (д.)")
            st.plotly_chart(fig_lt, use_container_width=True, key="chart_periods_lt")

        with c_g2:
            fig_work_wait = px.bar(
                cmp_df,
                x="Период",
                y=["Чистая работа Ср (д.)", "Очереди Ср (д.)"],
                barmode="group",
                title="Соотношение чистой работы и очередей (д.)",
                text_auto=".2f",
                color_discrete_sequence=["#2ca02c", "#d62728"]
            )
            fig_work_wait.update_layout(height=360, yaxis_title="Рабочие дни (д.)")
            st.plotly_chart(fig_work_wait, use_container_width=True, key="chart_periods_work_wait")

        st.markdown("---")
<<<<<<< HEAD
        st.markdown("#### 2. Динамика метрик и Flow по ролям")
=======
        st.markdown("#### 2. Сравнение метрик и Flow по ролям")
>>>>>>> c7b0efa56c7e205b1b045fcc5a20a4380bdd34e3

        role_tab_qa, role_tab_dev, role_tab_an = st.tabs([
            "🧪 Тестирование (QA)",
            "💻 Разработка (Dev)",
            "📐 Аналитика (Analytics)",
        ])

        with role_tab_qa:
            qa_cmp_cols = ["Период", "QA В тестировании Ср (д.)", "QA Очередь Ср (д.)", "QA Циклтайм Ср (д.)", "QA Flow (%)"]
            st.dataframe(cmp_df[qa_cmp_cols], use_container_width=True, hide_index=True)
            fig_qa_cmp = px.bar(
                cmp_df,
                x="Период",
                y=["QA В тестировании Ср (д.)", "QA Очередь Ср (д.)", "QA Циклтайм Ср (д.)"],
                barmode="group",
                title="Динамика этапа QA (в днях)",
                text_auto=".2f",
                color_discrete_sequence=["#2ca02c", "#d62728", "#1f77b4"]
            )
            fig_qa_cmp.update_layout(height=350, yaxis_title="Рабочие дни (д.)")
            st.plotly_chart(fig_qa_cmp, use_container_width=True, key="chart_periods_qa_cmp")

        with role_tab_dev:
            dev_cmp_cols = ["Период", "Dev В разработке Ср (д.)", "Dev Очередь/Ревью Ср (д.)", "Dev Цикл Ср (д.)", "Dev Flow (%)"]
            st.dataframe(cmp_df[dev_cmp_cols], use_container_width=True, hide_index=True)
            fig_dev_cmp = px.bar(
                cmp_df,
                x="Период",
                y=["Dev В разработке Ср (д.)", "Dev Очередь/Ревью Ср (д.)", "Dev Цикл Ср (д.)"],
                barmode="group",
                title="Динамика этапа разработки (в днях)",
                text_auto=".2f",
                color_discrete_sequence=["#1f77b4", "#ff7f0e", "#9467bd"]
            )
            fig_dev_cmp.update_layout(height=350, yaxis_title="Рабочие дни (д.)")
            st.plotly_chart(fig_dev_cmp, use_container_width=True, key="chart_periods_dev_cmp")

        with role_tab_an:
            an_cmp_cols = ["Период", "An В аналитике Ср (д.)", "An Очередь/Ревью Ср (д.)", "An Цикл Ср (д.)", "An Flow (%)"]
            st.dataframe(cmp_df[an_cmp_cols], use_container_width=True, hide_index=True)
            fig_an_cmp = px.bar(
                cmp_df,
                x="Период",
                y=["An В аналитике Ср (д.)", "An Очередь/Ревью Ср (д.)", "An Цикл Ср (д.)"],
                barmode="group",
                title="Динамика этапа аналитики (в днях)",
                text_auto=".2f",
                color_discrete_sequence=["#aec7e8", "#ffbb78", "#2ca02c"]
            )
            fig_an_cmp.update_layout(height=350, yaxis_title="Рабочие дни (д.)")
            st.plotly_chart(fig_an_cmp, use_container_width=True, key="chart_periods_an_cmp")
    else:
<<<<<<< HEAD
        st.info("Нет завершённых задач в выбранных периодах.")
=======
        st.info("Недостаточно данных для построения сравнительного анализа.")
>>>>>>> c7b0efa56c7e205b1b045fcc5a20a4380bdd34e3
