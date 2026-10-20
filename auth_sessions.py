"""Постоянные отзываемые сессии. В базе хранятся только хэши токенов."""
import hashlib
import hmac
import re
import secrets
import time

from psycopg_pool import ConnectionPool

SESSION_TTL = 7 * 24 * 60 * 60


class SessionStore:
    def __init__(self, pool: ConnectionPool, *, clock=time.time):
        self.pool = pool
        self.clock = clock
        with self.pool.connection() as conn:
            conn.execute(
                "SELECT pg_advisory_xact_lock("
                "hashtext('team_process_analytics_schema')::bigint)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash text PRIMARY KEY,
                    username text NOT NULL,
                    credential_hash text NOT NULL,
                    expires_at bigint NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires "
                "ON auth_sessions (expires_at)"
            )

    @staticmethod
    def _hash(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def create(self, username, credential_hash):
        token = secrets.token_urlsafe(32)
        now = int(self.clock())
        with self.pool.connection() as conn:
            conn.execute(
                "DELETE FROM auth_sessions WHERE expires_at <= %s", (now,)
            )
            conn.execute(
                "INSERT INTO auth_sessions (token_hash, username, credential_hash, expires_at) "
                "VALUES (%s, %s, %s, %s)",
                (self._hash(token), username, credential_hash, now + SESSION_TTL),
            )
        return token

    def resolve(self, token, users):
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            return None
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT username, credential_hash, expires_at "
                "FROM auth_sessions WHERE token_hash = %s",
                (self._hash(token),),
            ).fetchone()
        if not row or row[2] <= int(self.clock()):
            return None
        user = users.get(row[0])
        if not user or not hmac.compare_digest(row[1], user['password_hash']):
            return None
        return row[0]

    def revoke(self, token):
        if isinstance(token, str):
            with self.pool.connection() as conn:
                conn.execute(
                    "DELETE FROM auth_sessions WHERE token_hash = %s",
                    (self._hash(token),),
                )
