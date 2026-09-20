"""ui/components.py — Универсальные элементы интерфейса."""
import pandas as pd
import streamlit as st


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