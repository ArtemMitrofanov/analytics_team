"""db.py — PostgreSQL хранение событий задач с дедупликацией по row_hash."""
import hashlib
import io
import os
import threading
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import psycopg
from psycopg_pool import ConnectionPool, PoolTimeout

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
EVENT_COLUMNS = [
    "task_id",
    "timestamp",
    "changed_value",
    "added_values",
    "removed_values",
    "author_full_name",
    "activity_type",
    "source_file",
    "file_hash",
    "row_hash",
]
_TEXT_COLUMNS = [
    "task_id",
    "changed_value",
    "added_values",
    "removed_values",
    "author_full_name",
    "activity_type",
    "source_file",
    "file_hash",
    "row_hash",
]

_pool: ConnectionPool | None = None
_pool_dsn: str | None = None
_pool_lock = threading.Lock()
_schema_lock = threading.Lock()
_schema_ready: set[int] = set()


def get_dsn() -> str:
    """Вернуть строку подключения PostgreSQL из окружения."""
    dsn = os.getenv("ANALYTICS_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError(
            "Не задан ANALYTICS_DATABASE_URL. "
            "Пример: postgresql://analytics:password@127.0.0.1:5432/analytics"
        )
    return dsn


def get_pool() -> ConnectionPool:
    """Лениво создать общий пул соединений с PostgreSQL."""
    global _pool, _pool_dsn
    dsn = get_dsn()
    with _pool_lock:
        if _pool is not None and _pool_dsn == dsn:
            return _pool
        if _pool is not None:
            _pool.close()
            _schema_ready.clear()
        pool = ConnectionPool(
            dsn,
            min_size=1,
            max_size=10,
            timeout=10,
            max_idle=300,
            check=ConnectionPool.check_connection,
            open=False,
            kwargs={"application_name": "team_process_analytics"},
        )
        try:
            pool.open(wait=True, timeout=10)
        except PoolTimeout as exc:
            pool.close()
            try:
                psycopg.connect(dsn, connect_timeout=5).close()
            except Exception as connect_error:
                raise RuntimeError(
                    f"Не удалось подключиться к PostgreSQL: {connect_error}"
                ) from connect_error
            raise RuntimeError("Пул PostgreSQL не инициализировался") from exc
        except Exception:
            pool.close()
            raise
        _pool = pool
        _pool_dsn = dsn
        return pool


def close_pool() -> None:
    """Закрыть пул (используется при завершении тестов и приложений)."""
    global _pool, _pool_dsn
    with _pool_lock:
        if _pool is not None:
            _pool.close()
        _pool = None
        _pool_dsn = None
        _schema_ready.clear()


def init_schema(pool: ConnectionPool | None = None) -> None:
    """Создать таблицы и индексы при первом подключении."""
    target = pool or get_pool()
    key = id(target)
    if key in _schema_ready:
        return
    with _schema_lock:
        if key in _schema_ready:
            return
        statements = [
            statement.strip()
            for statement in SCHEMA_PATH.read_text(encoding="utf-8").split(";")
            if statement.strip()
        ]
        with target.connection() as conn:
            conn.execute(
                "SELECT pg_advisory_xact_lock("
                "hashtext('team_process_analytics_schema')::bigint)"
            )
            for statement in statements:
                conn.execute(statement)
        _schema_ready.add(key)


@contextmanager
def _connection():
    """Соединение из пула; транзакция коммитится при успешном выходе."""
    pool = get_pool()
    init_schema(pool)
    with pool.connection() as conn:
        yield conn


def _normalize_event_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Сохранить datetime-типы даже для пустого результата запроса."""
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    if "loaded_at" in df.columns:
        df["loaded_at"] = pd.to_datetime(df["loaded_at"], errors="coerce", utc=True)
    return df


def _read_df(conn, sql: str, params=None) -> pd.DataFrame:
    cur = conn.execute(sql, params) if params is not None else conn.execute(sql)
    columns = [column.name for column in cur.description] if cur.description else []
    return _normalize_event_dtypes(pd.DataFrame(cur.fetchall(), columns=columns))


def make_row_hash(row: pd.Series) -> str:
    """
    Уникальный хэш строки по бизнес-ключам.
    Используем: task_id + timestamp + changed_value + added_values + removed_values + author_full_name
    """
    key_parts = [
        str(row.get("task_identifier") or row.get("task_id") or row.get("issue_id") or ""),
        str(row.get("timestamp") or ""),
        str(row.get("changed_value") or ""),
        str(row.get("added_values") or ""),
        str(row.get("removed_values") or ""),
        str(row.get("author_full_name") or ""),
    ]
    key = "|".join(key_parts)
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def make_file_hash(content: bytes) -> str:
    """Хэш всего файла для быстрой проверки 'уже загружен'."""
    return hashlib.md5(content).hexdigest()


def is_file_loaded(file_hash: str) -> bool:
    """Проверить, загружен ли файл с таким хэшем."""
    with _connection() as conn:
        row = conn.execute(
            "SELECT EXISTS(SELECT 1 FROM task_events WHERE file_hash = %s)",
            (file_hash,),
        ).fetchone()
    return bool(row and row[0])


def _prepare_for_copy(df: pd.DataFrame) -> pd.DataFrame:
    """Привести DataFrame к типам, которые принимает COPY в PostgreSQL."""
    if "timestamp" not in df.columns:
        return df.head(0)
    if getattr(df["timestamp"].dt, "tz", None) is not None:
        df["timestamp"] = df["timestamp"].dt.tz_localize(None)
    df["timestamp"] = [value.to_pydatetime() for value in df["timestamp"]]
    for column in _TEXT_COLUMNS:
        df[column] = df[column].map(lambda value: None if pd.isna(value) else str(value))
    return df


def load_dataframe_to_db(df: pd.DataFrame, source_file: str, file_hash: str) -> int:
    """
    Загрузить DataFrame в PostgreSQL с дедупликацией по row_hash.
    Возвращает количество реально добавленных строк.
    """
    if df.empty:
        return 0

    df = df.copy()

    if "task_identifier" in df.columns:
        df["task_id"] = df["task_identifier"]
    elif "issue_id" in df.columns:
        df["task_id"] = df["issue_id"]
    elif "iissue_id" in df.columns:
        df["task_id"] = df["iissue_id"]

    # row_hash считается по исходным значениям — так же, как в прежней DuckDB-версии.
    df["row_hash"] = df.apply(make_row_hash, axis=1)
    df["source_file"] = source_file
    df["file_hash"] = file_hash

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    for column in ("added_values", "removed_values", "author_full_name", "activity_type"):
        if column not in df.columns:
            df[column] = ""

    df = df[EVENT_COLUMNS].dropna(subset=["task_id", "timestamp", "changed_value"])
    if df.empty:
        return 0

    df = _prepare_for_copy(df)
    column_sql = ", ".join(
        f'"{column}"' if column == "timestamp" else column for column in EVENT_COLUMNS
    )

    with _connection() as conn:
        conn.execute(
            "CREATE TEMP TABLE _task_events_staging ON COMMIT DROP "
            "AS SELECT * FROM task_events WITH NO DATA"
        )
        buffer = io.StringIO()
        df[EVENT_COLUMNS].to_csv(
            buffer, index=False, header=False, lineterminator="\n", na_rep="\\N"
        )
        buffer.seek(0)
        with conn.cursor() as cur:
            with cur.copy(
                f"COPY _task_events_staging ({column_sql}) "
                "FROM STDIN WITH (FORMAT csv, NULL '\\N')"
            ) as copy:
                while chunk := buffer.read(1024 * 1024):
                    copy.write(chunk)
            cur.execute(
                f"""
                INSERT INTO task_events ({column_sql})
                SELECT {column_sql} FROM _task_events_staging
                ON CONFLICT (row_hash) DO NOTHING
                RETURNING 1
                """
            )
            return len(cur.fetchall())


def get_db_fingerprint() -> str:
    """Короткий отпечаток содержимого БД для ключа кэша pipeline."""
    with _connection() as conn:
        row = conn.execute(
            'SELECT COUNT(*), MAX(loaded_at), MAX("timestamp") FROM task_events'
        ).fetchone()
    if not row:
        return "empty"
    return f"{row[0]}|{row[1] or ''}|{row[2] or ''}"


def get_all_events() -> pd.DataFrame:
    """Получить все события для аналитики."""
    with _connection() as conn:
        return _read_df(
            conn,
            'SELECT * FROM task_events ORDER BY task_id, "timestamp"',
        )


def get_events_for_tasks(task_ids: list[str]) -> pd.DataFrame:
    """Получить события для списка задач."""
    if not task_ids:
        return _normalize_event_dtypes(
            pd.DataFrame(columns=EVENT_COLUMNS + ["loaded_at"])
        )
    with _connection() as conn:
        return _read_df(
            conn,
            'SELECT * FROM task_events '
            'WHERE task_id = ANY(%s) ORDER BY task_id, "timestamp"',
            ([str(task_id) for task_id in task_ids],),
        )


def get_summary_stats() -> dict:
    """Базовая статистика по БД."""
    with _connection() as conn:
        stats = conn.execute(
            """
            SELECT
                COUNT(*) AS total_rows,
                COUNT(DISTINCT task_id) AS unique_tasks,
                COUNT(DISTINCT source_file) AS loaded_files,
                MIN("timestamp") AS earliest_event,
                MAX("timestamp") AS latest_event,
                MAX(loaded_at) AS last_load
            FROM task_events
            """
        ).fetchone()
    return {
        "total_rows": stats[0],
        "unique_tasks": stats[1],
        "loaded_files": stats[2],
        "earliest_event": stats[3],
        "latest_event": stats[4],
        "last_load": stats[5],
    }


def clear_database() -> None:
    """Полная очистка (для тестов/перезагрузки)."""
    with _connection() as conn:
        conn.execute("TRUNCATE TABLE task_events")
