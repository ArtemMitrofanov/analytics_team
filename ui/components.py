"""ui/components.py — Универсальные элементы интерфейса."""
import pandas as pd
import streamlit as st
from crewai import Agent, Crew, LLM, Task
from config import DEFAULT_CREWAI_MODEL


def render_searchable_log(log_df: pd.DataFrame, task_col: str, title: str, csv_name: str, key_suffix: str):
    st.markdown(f"##### 📋 {title}")
    if not log_df.empty and task_col in log_df.columns:
        c1, c2 = st.columns([1, 1])
        with c1:
            search_q = st.text_input("🔍 Быстрый поиск по задаче:", placeholder="Например: 2280", key=f"search_{key_suffix}")
        available = sorted(log_df[task_col].dropna().unique())
        with c2:
            selected_t = st.multiselect("Выбрать из списка:", options=available, default=[], key=f"multi_{key_suffix}")

        filtered = log_df.copy()
        if search_q.strip():
            filtered = filtered[filtered[task_col].astype(str).str.contains(search_q.strip(), case=False, na=False)]
        if selected_t:
            filtered = filtered[filtered[task_col].isin(selected_t)]

        st.caption(f"Найдено записей: **{len(filtered)}** из **{len(log_df)}**")
        st.dataframe(filtered, use_container_width=True, hide_index=True)
        csv_exp = filtered.to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 Скачать журнал (CSV)", csv_exp, csv_name, "text/csv", key=f"dl_{key_suffix}")
    else:
        st.info("В выбранном периоде нет записей для этого журнала.")


def render_ai_audit_button(
    button_label: str,
    key_suffix: str,
    agent_role: str,
    agent_goal: str,
    context_prompt: str,
    gemini_key: str,
    backstory: str = "Senior Delivery & Engineering Optimization Expert."
):
    """Отображает кнопку ИИ-аудита с запуском агента CrewAI."""
    st.markdown("---")
    c_btn, c_hint = st.columns([1, 3])
    with c_btn:
        btn_clicked = st.button(f"🤖 {button_label}", key=f"ai_btn_{key_suffix}")
    with c_hint:
        if not gemini_key:
            st.caption("ℹ️ Для активации кнопки укажите Gemini API Key в боковой панели.")

    if btn_clicked:
        if not gemini_key:
            st.warning("⚠️ Пожалуйста, введите Gemini API Key в боковой панели слева.")
            return

        with st.spinner(f"Агент «{agent_role}» анализирует показатели..."):
            try:
                llm = LLM(model=DEFAULT_CREWAI_MODEL, api_key=gemini_key, temperature=0.2)
                agent = Agent(
                    role=agent_role,
                    goal=agent_goal,
                    backstory=backstory,
                    llm=llm
                )
                task = Task(
                    description=(
                        f"Ты профессиональный эксперт по оптимизации процессов.\n"
                        f"Проанализируй следующие метрики команды:\n{context_prompt}\n\n"
                        f"Сформулируй 3 конкретные, прикладные рекомендации с обоснованием: "
                        f"где кроется главная потеря времени и какие действия предпринять команде."
                    ),
                    expected_output="3 структурированные инженерно-процессные рекомендации с выводами.",
                    agent=agent
                )
                crew = Crew(agents=[agent], tasks=[task])
                result = crew.kickoff()
                st.success("✅ ИИ-аудит успешно завершен!")
                st.markdown(result.raw)
            except Exception as err:
                st.error(f"Ошибка при обращении к ИИ: {err}")