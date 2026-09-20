"""ui/tabs/estimates.py — Анализ точности и калибровка T-Shirt размеров."""
import pandas as pd
import plotly.express as px
import streamlit as st
from config import TSHIRT_ORDER, CORE_QA_TEAM, CORE_DEV_TEAM, CORE_ANALYTICS_TEAM
from utils.stats import calc_stats


def render_estimates_tab(
    summary_df: pd.DataFrame,
    qa_iter_df: pd.DataFrame,
    dev_iter_df: pd.DataFrame,
    an_iter_df: pd.DataFrame
):
    st.subheader("🎯 Анализ точности и калибровка оценок задач (T-Shirt Sizes)")
    st.caption("Сопоставление плановых и фактических размеров (XS, S, M, L, XL) и калибровка фактическими рабочими днями")

    est_df = summary_df.copy()

    def eval_accuracy(plan_col: str, fact_col: str, data: pd.DataFrame):
        if plan_col not in data.columns or fact_col not in data.columns:
            return 0, 0.0, 0.0, 0.0
        valid = data[(data[plan_col].isin(TSHIRT_ORDER)) & (data[fact_col].isin(TSHIRT_ORDER))]
        if valid.empty:
            return 0, 0.0, 0.0, 0.0
        total = len(valid)
        order_map = {k: i for i, k in enumerate(TSHIRT_ORDER)}
        exact = (valid[plan_col] == valid[fact_col]).sum()
        under = (valid[fact_col].map(order_map) > valid[plan_col].map(order_map)).sum()
        over = (valid[fact_col].map(order_map) < valid[plan_col].map(order_map)).sum()
        return total, (exact / total * 100), (under / total * 100), (over / total * 100)

    tot_d, acc_d, under_d, _ = eval_accuracy("dev_plan", "dev_fact", est_df)
    tot_q, acc_q, under_q, _ = eval_accuracy("qa_plan", "qa_fact", est_df)
    tot_a, acc_a, under_a, _ = eval_accuracy("an_plan", "an_fact", est_df)

    e1, e2, e3, e4 = st.columns(4)
    avg_acc = (acc_d + acc_q + acc_a) / 3 if (tot_d or tot_q or tot_a) else 0.0
    avg_under = (under_d + under_q + under_a) / 3 if (tot_d or tot_q or tot_a) else 0.0

    e1.metric("Точность эстимации (План=Факт)", f"{avg_acc:.1f}%")
    e2.metric("Недооценка сложности (Факт > План)", f"{avg_under:.1f}%", delta_color="inverse")
    e3.metric("Задач с оценкой разработки", f"{tot_d} шт")
    e4.metric("Задач с оценкой QA", f"{tot_q} шт")

    st.markdown("---")
    st.markdown("#### 1. Калибровка T-Shirt размеров фактическими днями")

    est_role_qa, est_role_dev, est_role_an = st.tabs([
        "🧪 Тестирование (QA)",
        "💻 Разработка (Dev)",
        "📐 Аналитика (Analytics)",
    ])

    def render_calibration(role_name: str, plan_col: str, fact_col: str, days_col: str, data: pd.DataFrame, iter_df: pd.DataFrame = None, core_team: list = None, actor_col: str = "Исполнитель"):
        col_tbl, col_chart = st.columns([1, 1])
        cal_rows = []
        for sz in TSHIRT_ORDER:
            sub = data[data[fact_col] == sz] if fact_col in data.columns else pd.DataFrame()
            cnt = len(sub)
            if cnt > 0:
                mean_d, med_d, p85_d, _ = calc_stats(sub.get(days_col, pd.Series(dtype=float)))
            else:
                mean_d = med_d = p85_d = 0.0
            cal_rows.append({
                "Размер": sz,
                "Задач (шт)": cnt,
                "Среднее (д.)": round(mean_d, 2),
                "Медиана (д.)": round(med_d, 2),
                "P85 SLE (д.)": round(p85_d, 2),
            })
        cal_df = pd.DataFrame(cal_rows)
        with col_tbl:
            st.markdown(f"**Эталонные ориентиры {role_name} (по фактическому размеру):**")
            st.dataframe(cal_df, use_container_width=True, hide_index=True)

        with col_chart:
            valid_counts = []
            for sz in TSHIRT_ORDER:
                p_cnt = (data[plan_col] == sz).sum() if plan_col in data.columns else 0
                f_cnt = (data[fact_col] == sz).sum() if fact_col in data.columns else 0
                valid_counts.append({"Размер": sz, "Тип": "План", "Количество": p_cnt})
                valid_counts.append({"Размер": sz, "Тип": "Факт", "Количество": f_cnt})
            fig_pf = px.bar(
                pd.DataFrame(valid_counts),
                x="Размер",
                y="Количество",
                color="Тип",
                barmode="group",
                title=f"Распределение {role_name}: План vs Факт",
                color_discrete_map={"План": "#1f77b4", "Факт": "#2ca02c"}
            )
            fig_pf.update_layout(height=300)
            st.plotly_chart(fig_pf, use_container_width=True, key=f"chart_estimates_dist_{role_name}")

        # Эффективность сотрудников по факт-оценке (для всех ролей) — только таблица
        if core_team is not None and iter_df is not None and not iter_df.empty and fact_col in data.columns:
            fact_map = data.set_index("Задача")[fact_col].to_dict()
            iter_enriched = iter_df.copy()
            iter_enriched["fact_value"] = iter_enriched["Задача"].map(fact_map)
            iter_enriched = iter_enriched[iter_enriched["fact_value"].notna() & (iter_enriched["fact_value"] != "")]

            if not iter_enriched.empty:
                # Детальная агрегация: по сотруднику И оценке
                eff = iter_enriched.groupby([actor_col, "fact_value"]).agg(
                    задач=("Задача", "nunique"),
                    сумм_дней=("Раб. дней", "sum"),
                ).reset_index()
                eff["среднее_дней"] = (eff["сумм_дней"] / eff["задач"]).round(2)
                eff = eff.sort_values([actor_col, "fact_value"])
                eff = eff.rename(columns={
                    actor_col: f"ФИО",
                    "fact_value": f"Оценка факт",
                    "задач": "Задач (шт)",
                    "сумм_дней": "Сумма дней",
                    "среднее_дней": f"Среднее время (д.)",
                })
                
                # Фильтруем только core team из config/team.json
                eff = eff[eff["ФИО"].isin(core_team)]
                
                if not eff.empty:
                    # Отдельные таблицы по каждому сотруднику
                    for person in eff["ФИО"].unique():
                        person_data = eff[eff["ФИО"] == person].drop(columns=["ФИО"])
                        st.markdown(f"**{person}**")
                        st.dataframe(person_data, use_container_width=True, hide_index=True)
                else:
                    st.info(f"Нет данных по участникам Core Team для текущего периода.")
            else:
                st.info(f"Нет данных по фактическим оценкам для текущего периода.")

    with est_role_qa:
        render_calibration("QA", "qa_plan", "qa_fact", "В тестировании (дни)", est_df, qa_iter_df, CORE_QA_TEAM, "Исполнитель")

    with est_role_dev:
        render_calibration("Разработки", "dev_plan", "dev_fact", "В разработке (д.)", est_df, dev_iter_df, CORE_DEV_TEAM, "Разработчик")

    with est_role_an:
        render_calibration("Аналитики", "an_plan", "an_fact", "В аналитике (д.)", est_df, an_iter_df, CORE_ANALYTICS_TEAM, "Аналитик")

    st.markdown("---")
    st.markdown("#### 2. Реестр оценок по задачам")

    filter_mismatch = st.checkbox("Показать только задачи с несовпадением Плана и Факта", value=False)

    base_cols = ["Задача", "task_size", "an_plan", "an_fact", "В аналитике (д.)", "dev_plan", "dev_fact", "В разработке (д.)", "qa_plan", "qa_fact", "В тестировании (дни)", "Полный Lead Time (д.)"]
    existing_cols = [c for c in base_cols if c in est_df.columns]
    tbl_est = est_df[existing_cols].copy()

    rename_dict = {
        "task_size": "Размер задачи",
        "an_plan": "План Аналитика", "an_fact": "Факт Аналитика", "В аналитике (д.)": "Дней в аналитике",
        "dev_plan": "План Dev", "dev_fact": "Факт Dev", "В разработке (д.)": "Дней в dev",
        "qa_plan": "План QA", "qa_fact": "Факт QA", "В тестировании (дни)": "Дней в QA"
    }
    tbl_est = tbl_est.rename(columns={k: v for k, v in rename_dict.items() if k in tbl_est.columns})

    if filter_mismatch and "План Dev" in tbl_est.columns and "Факт Dev" in tbl_est.columns:
        tbl_est = tbl_est[
            (tbl_est.get("План Dev") != tbl_est.get("Факт Dev"))
            | (tbl_est.get("План QA") != tbl_est.get("Факт QA"))
            | (tbl_est.get("План Аналитика") != tbl_est.get("Факт Аналитика"))
        ]

    search_est_q = st.text_input("🔍 Быстрый поиск задачи по номеру:", placeholder="Например: 2421", key="search_est_table")
    if search_est_q.strip():
        tbl_est = tbl_est[tbl_est["Задача"].astype(str).str.contains(search_est_q.strip(), case=False, na=False)]

    st.caption(f"Отображено задач: **{len(tbl_est)}** из **{len(est_df)}**")
    st.dataframe(tbl_est, use_container_width=True, hide_index=True)

    csv_est_exp = tbl_est.to_csv(index=False).encode("utf-8-sig")
    st.download_button("📥 Скачать реестр оценок (CSV)", csv_est_exp, "task_estimations.csv", "text/csv")