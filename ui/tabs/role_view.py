"""ui/tabs/role_view.py — Универсальный шаблон рендеринга аудита направления (QA/Dev/Analytics)."""
from typing import List
import pandas as pd
import streamlit as st
from utils.stats import calc_stats
from ui.components import render_searchable_log
from crewai import Agent, Crew, LLM, Task
from config import DEFAULT_CREWAI_MODEL

def render_role_tab(
    role_title: str,
    work_status_col: str,
    queue_status_col: str,
    cycle_col: str,
    flow_col: str,
    table_cols: List[str],
    iter_df: pd.DataFrame,
    rev_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    actor_col_name: str,
    gemini_key: str,
    net_day_hours: float,
    reworks_df: pd.DataFrame = None,
    ai_agent_role: str = "",
    ai_goal: str = ""
):
    st.subheader(f"Аудит направления: {role_title}")
    sub_tabs = st.tabs([
        f"📊 Метрики и Flow {role_title}",
        f"👥 Аналитика по сотрудникам",
        "🔍 Анализ Ревью / Доработок",
        f"📋 Журнал итераций",
    ])

    with sub_tabs[0]:
        act_df = summary_df[summary_df[work_status_col] > 0] if work_status_col in summary_df else summary_df
        w_m, w_med, w_p85, _ = calc_stats(act_df.get(work_status_col, pd.Series(dtype=float)))
        q_m, q_med, q_p85, _ = calc_stats(act_df.get(queue_status_col, pd.Series(dtype=float)))
        c_m, c_med, c_p85, _ = calc_stats(act_df.get(cycle_col, pd.Series(dtype=float)))
        f_m, f_med, f_p85, _ = calc_stats(act_df.get(flow_col, pd.Series(dtype=float)))

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("В работе", f"{w_m:.2f} д.", f"Мед: {w_med:.2f} | P85: {w_p85:.2f}")
        c2.metric("Очередь / Ревью", f"{q_m:.2f} д.", f"Мед: {q_med:.2f} | P85: {q_p85:.2f}", delta_color="inverse")
        c3.metric("Цикл этапа", f"{c_m:.2f} д.", f"Мед: {c_med:.2f} | P85: {c_p85:.2f}")
        c4.metric("Flow этапа", f"{f_m:.1f}%", f"Мед: {f_med:.1f}% | P85: {f_p85:.1f}%")

        st.markdown("---")
        st.markdown("##### Сводная таблица по задачам (в днях)")
        metric_cols = [c for c in table_cols if c != "Задача" and c in summary_df.columns]
        table_filtered = summary_df[table_cols][(summary_df[metric_cols] > 0).any(axis=1)]
        if not table_filtered.empty:
            st.dataframe(table_filtered, use_container_width=True, hide_index=True)
        else:
            st.info(f"В выбранном периоде нет активности по направлению {role_title}.")

        # Кнопка ИИ-аудита
        if gemini_key and ai_agent_role and st.button(f"🚀 ИИ-аудит {role_title} (CrewAI)", key=f"btn_ai_{role_title}"):
            with st.spinner(f"Агент анализирует процесс {role_title}..."):
                try:
                    llm = LLM(model=DEFAULT_CREWAI_MODEL, api_key=gemini_key, temperature=0.2)
                    agent = Agent(role=ai_agent_role, goal=ai_goal, backstory="Senior Delivery Expert", llm=llm)
                    t = Task(
                        description=f"Метрики {role_title} (1 р.д.={net_day_hours:.1f}ч): В работе ср={w_m:.2f}д (P85={w_p85:.2f}д), Очередь={q_m:.2f}д, Flow={f_m:.1f}%. Сформулируй 3 рекомендации.",
                        expected_output="3 рекомендации.",
                        agent=agent
                    )
                    res = Crew(agents=[agent], tasks=[t]).kickoff()
                    st.success("Аудит завершен!")
                    st.markdown(res.raw)
                except Exception as err:
                    st.error(f"Ошибка ИИ: {err}")

    with sub_tabs[1]:
        if not iter_df.empty and actor_col_name in iter_df.columns:
            grp = iter_df.groupby(actor_col_name).agg(
                tasks=("Задача", "nunique"), iters=("Итерация", "count"), days=("Раб. дней", "sum")
            ).reset_index()
            grp["avg_per_task"] = (grp["days"] / grp["tasks"]).round(2)
            grp = grp.rename(columns={"tasks": "Задач (шт)", "iters": "Подходов (шт)", "days": "Суммарно (д.)", "avg_per_task": "Среднее на задачу (д.)"})
            st.dataframe(grp, use_container_width=True, hide_index=True)
        else:
            st.info("Нет данных по исполнителям.")

    with sub_tabs[2]:
        if reworks_df is not None and not reworks_df.empty:
            st.markdown("##### 🔧 Возвраты на доработку")
            st.dataframe(reworks_df, use_container_width=True, hide_index=True)
        elif not rev_df.empty:
            st.markdown("##### 🔍 Анализ задержек ревью")
            rev_summary = rev_df.groupby("Этап ревью").agg(
                tasks=("Задача", "nunique"), total_days=("Длительность (д.)", "sum"), avg_days=("Длительность (д.)", "mean")
            ).reset_index()
            st.dataframe(rev_summary, use_container_width=True, hide_index=True)
            st.markdown("###### Лог событий:")
            st.dataframe(rev_df, use_container_width=True, hide_index=True)
        else:
            st.info("Нет зафиксированных данных ревью/доработок.")

    with sub_tabs[3]:
        render_searchable_log(iter_df, "Задача", f"Журнал итераций {role_title}", f"{role_title}_iters.csv", f"log_{role_title}")