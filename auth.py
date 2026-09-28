"""auth.py — Аутентификация и управление сессией."""
import streamlit as st
from access_control import (
    get_user_role, get_available_tabs, get_tab_labels,
    verify_password, get_all_users, get_user_display_name
)
from access_control import Role


def render_login_page() -> bool:
    """Рендерит страницу входа в центре экрана. Возвращает True если авторизован."""
    # Если уже залогинен — возвращаем True (информацию в сайдбаре рисует render_user_info_sidebar)
    if "user_name" in st.session_state:
        return True

    # Центрированная форма входа
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("## 🔐 Вход в систему")
        st.markdown("---")

        all_users = get_all_users()

        with st.form("login_form", clear_on_submit=False):
            user_name = st.selectbox(
                "Выберите пользователя:",
                options=[""] + all_users,
                placeholder="Выберите из списка...",
                format_func=lambda x: get_user_display_name(x) if x else "Выберите из списка...",
            )
            password = st.text_input("Пароль:", type="password", placeholder="Введите пароль")
            submitted = st.form_submit_button("Войти", type="primary", use_container_width=True)

            if submitted:
                if not user_name:
                    st.error("Выберите пользователя")
                elif not password:
                    st.error("Введите пароль")
                elif verify_password(user_name, password):
                    st.session_state.user_name = user_name
                    st.session_state.user_role = get_user_role(user_name)
                    st.success("✅ Успешный вход!")
                    st.rerun()
                else:
                    st.error("❌ Неверный пароль")

    st.stop()
    return False


def render_user_info_sidebar():
    """Рендерит информацию о пользователе в самом верху сайдбара."""
    if "user_name" not in st.session_state:
        return

    with st.sidebar:
        st.markdown("### 👤 Пользователь")
        display_name = get_user_display_name(st.session_state.user_name)
        st.success(f"**{display_name}**")
        st.caption(f"Роль: {st.session_state.user_role}")
        if st.button("Выйти", type="secondary", use_container_width=True):
            for key in ["user_name", "user_role"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
        st.markdown("---")


def filter_summary_by_role(summary_df, role: Role, user_name: str):
    """Фильтрует summary_df по роли пользователя (для роли viewer/qa/dev/analytics)."""
    if role == "admin":
        return summary_df

    if role == "qa":
        return summary_df[summary_df.get("В тестировании (дни)", 0) > 0]

    if role == "dev":
        return summary_df[summary_df.get("В разработке (д.)", 0) > 0]

    if role == "analytics":
        return summary_df[summary_df.get("В аналитике (д.)", 0) > 0]

    return summary_df.head(0)


def filter_iter_df_by_role(iter_df, role: Role, user_name: str):
    """Фильтрует итерации по исполнителю для роли."""
    if role == "admin":
        return iter_df

    actor_cols = {
        "qa": "Исполнитель",
        "dev": "Разработчик",
        "analytics": "Аналитик",
    }

    actor_col = actor_cols.get(role)
    if actor_col and actor_col in iter_df.columns:
        return iter_df[iter_df[actor_col] == user_name]

    return iter_df