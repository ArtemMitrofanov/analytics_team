import hashlib

import pytest

from auth_sessions import SESSION_TTL, SessionStore
from db import get_pool, init_schema


@pytest.fixture
def sessions(database_url):
    now = [1000]
    users = {"admin": {"password_hash": hashlib.sha256(b"password").hexdigest(), "role": "admin"}}
    pool = get_pool()
    init_schema(pool)
    with pool.connection() as conn:
        conn.execute("TRUNCATE TABLE auth_sessions")
    store = SessionStore(pool, clock=lambda: now[0])
    yield store, users, now
    with pool.connection() as conn:
        conn.execute("TRUNCATE TABLE auth_sessions")


def test_session_survives_new_store_instance(sessions):
    store, users, now = sessions
    token = store.create("admin", users["admin"]["password_hash"])
    reopened = SessionStore(store.pool, clock=lambda: now[0])
    assert reopened.resolve(token, users) == "admin"
    with store.pool.connection() as conn:
        assert conn.execute("SELECT token_hash FROM auth_sessions").fetchone()[0] != token


def test_invalid_and_tampered_tokens_are_rejected(sessions):
    store, users, _ = sessions
    token = store.create("admin", users["admin"]["password_hash"])
    for invalid in [None, "", "admin", token[:-1], ("a" if token[0] != "a" else "b") + token[1:], "x" * 10000]:
        assert store.resolve(invalid, users) is None


def test_expiry_and_password_change_invalidate_session(sessions):
    store, users, now = sessions
    token = store.create("admin", users["admin"]["password_hash"])
    now[0] += SESSION_TTL
    assert store.resolve(token, users) is None
    now[0] = 1000
    users["admin"]["password_hash"] = hashlib.sha256(b"new password").hexdigest()
    assert store.resolve(token, users) is None
    assert store.resolve(token, {}) is None


def test_logout_revokes_only_current_session(sessions):
    store, users, _ = sessions
    first = store.create("admin", users["admin"]["password_hash"])
    other = store.create("admin", users["admin"]["password_hash"])
    store.revoke(first)
    assert store.resolve(first, users) is None
    assert store.resolve(other, users) == "admin"
