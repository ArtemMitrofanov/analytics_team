import pytest
from streamlit.testing.v1 import AppTest

import auth
from access_control import USERS
from auth_sessions import SessionStore
from db import get_pool, init_schema

SOURCE = '''
import streamlit as st
from auth import render_login_page, render_user_info_sidebar
if render_login_page():
    render_user_info_sidebar()
    st.success("Авторизован")
'''


@pytest.fixture
def browser(database_url, monkeypatch):
    cookies = {}
    pool = get_pool()
    init_schema(pool)
    with pool.connection() as conn:
        conn.execute("TRUNCATE TABLE auth_sessions")
    store = SessionStore(pool)
    monkeypatch.setattr(auth, "_store", lambda: store)
    def component(**args):
        result = {"request_id": args["request_id"]}
        if args["operation"] == "read":
            result["token"] = cookies.get("token", "")
        elif args["operation"] == "set":
            cookies["token"] = args["token"]
            result["ok"] = True
        elif args["operation"] == "delete":
            cookies.clear()
            result["ok"] = True
        return result
    monkeypatch.setattr(auth, "cookie_component", component)
    yield cookies, store
    with pool.connection() as conn:
        conn.execute("TRUNCATE TABLE auth_sessions")


def test_login_refresh_logout_and_replay(browser):
    cookies, store = browser
    app = AppTest.from_string(SOURCE).run()
    assert not app.exception
    app.selectbox[0].select("admin")
    # В тесте известный пароль настраивается независимо от серверных пользователей.
    original_hash = USERS["admin"]["password_hash"]
    import hashlib
    USERS["admin"]["password_hash"] = hashlib.sha256(b"test password").hexdigest()
    try:
        app.text_input[0].input("test password")
        app.button[0].click().run()
        assert not app.exception
        assert app.session_state["user_name"] == "admin"
        token = cookies["token"]
        refreshed = AppTest.from_string(SOURCE).run()
        assert not refreshed.exception
        assert refreshed.session_state["user_name"] == "admin"
        assert len(refreshed.text_input) == 0
        refreshed.button[0].click().run()
        assert not refreshed.exception
        assert not cookies
        assert store.resolve(token, USERS) is None
        # Старый cookie после выхода больше не даёт доступа.
        cookies["token"] = token
        replay = AppTest.from_string(SOURCE).run()
        assert not replay.exception
        assert len(replay.text_input) == 1
    finally:
        USERS["admin"]["password_hash"] = original_hash


def test_browser_response_is_required_before_showing_login(browser, monkeypatch):
    monkeypatch.setattr(auth, "cookie_component", lambda **kwargs: None)
    app = AppTest.from_string(SOURCE).run()
    assert not app.exception
    assert len(app.text_input) == 0
