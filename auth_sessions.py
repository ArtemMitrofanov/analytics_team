"""Постоянные отзываемые сессии. В базе хранятся только хэши токенов."""
from contextlib import closing
import hashlib
import hmac
from pathlib import Path
import re
import secrets
import sqlite3
import time

SESSION_TTL = 7 * 24 * 60 * 60


class SessionStore:
    def __init__(self, path, *, clock=time.time):
        self.path = Path(path)
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=10)) as conn, conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                credential_hash TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            )''')

    @staticmethod
    def _hash(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def create(self, username, credential_hash):
        token = secrets.token_urlsafe(32)
        now = int(self.clock())
        with closing(sqlite3.connect(self.path, timeout=10)) as conn, conn:
            conn.execute('DELETE FROM auth_sessions WHERE expires_at <= ?', (now,))
            conn.execute('INSERT INTO auth_sessions VALUES (?, ?, ?, ?)',
                         (self._hash(token), username, credential_hash, now + SESSION_TTL))
        return token

    def resolve(self, token, users):
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            return None
        with closing(sqlite3.connect(self.path, timeout=10)) as conn:
            row = conn.execute('SELECT username, credential_hash, expires_at '
                               'FROM auth_sessions WHERE token_hash = ?',
                               (self._hash(token),)).fetchone()
        if not row or row[2] <= int(self.clock()):
            return None
        user = users.get(row[0])
        if not user or not hmac.compare_digest(row[1], user['password_hash']):
            return None
        return row[0]

    def revoke(self, token):
        if isinstance(token, str):
            with closing(sqlite3.connect(self.path, timeout=10)) as conn, conn:
                conn.execute('DELETE FROM auth_sessions WHERE token_hash = ?',
                             (self._hash(token),))
