"""auth.py — Аутентификация и управление сессией."""
import uuid
from pathlib import Path

import streamlit as st
from streamlit.components.v1 import declare_component

from access_control import (
    USERS,
    Role,
    get_all_users,
    get_user_display_name,
    get_user_role,
    verify_password,
)
from auth_sessions import SESSION_TTL, SessionStore
from db import get_pool

cookie_component = declare_component(
    "analytics_session_cookie", path=str(Path(__file__).parent / "ui" / "session_cookie")
)


@st.cache_resource
def _session_store():
    return SessionStore(get_pool())


def _store():
    return _session_store()


def _cookie_request(operation, **kwargs):
    st.session_state.auth_cookie_request = dict(
        operation=operation, request_id=uuid.uuid4().hex, **kwargs
    )


def _clear_login():
    for key in ("user_name", "user_role", "auth_session_token", "auth_pending_user"):
        st.session_state.pop(key, None)


def _restore_browser_session():
    if "auth_cookie_request" not in st.session_state:
        _cookie_request("read")
    request = st.session_state.auth_cookie_request
    response = cookie_component(**request, ttl=SESSION_TTL, key="auth_cookie", default=None)
    operation = request["operation"]
    if operation != "idle":
        if not isinstance(response, dict) or response.get("request_id") != request["request_id"]:
            st.caption("Восстанавливаем сессию…" if operation == "read" else "Сохраняем сессию…")
            st.stop()
        if operation == "read":
            token = response.get("token", "")
            username = _store().resolve(token, USERS)
            if username:
                st.session_state.user_name = username
                st.session_state.auth_session_token = token
        elif operation == "set":
            if response.get("ok"):
                st.session_state.user_name = st.session_state.auth_pending_user
                st.session_state.auth_session_token = request["token"]
            else:
                _store().revoke(request["token"])
                _clear_login()
                st.session_state.auth_cookie_error = "Браузер блокирует cookie. Разрешите cookie для этого сайта."
        elif operation == "delete":
            _clear_login()
        _cookie_request("idle")

    token = st.session_state.get("auth_session_token")
    username = _store().resolve(token, USERS)
    if username:
        st.session_state.user_name = username
        st.session_state.user_role = get_user_role(username)
        return True
    _clear_login()
    return False


def render_login_page() -> bool:
    """Рендерит страницу входа в центре экрана. Возвращает True если авторизован."""
    if _restore_browser_session():
        return True

    # Центрированная форма входа
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("## 🔐 Вход в систему")
        st.markdown("---")
        if st.session_state.get("auth_cookie_error"):
            st.error(st.session_state.auth_cookie_error)

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
                    token = _store().create(user_name, USERS[user_name]["password_hash"])
                    st.session_state.auth_pending_user = user_name
                    st.session_state.pop("auth_cookie_error", None)
                    _cookie_request("set", token=token)
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
            _store().revoke(st.session_state.get("auth_session_token"))
            _clear_login()
            _cookie_request("delete")
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
