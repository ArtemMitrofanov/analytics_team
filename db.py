"""db.py — DuckDB хранение событий задач с дедупликацией по row_hash."""
import hashlib
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

DB_PATH = Path(__file__).resolve().parent / "analytics.duckdb"


def get_conn() -> duckdb.DuckDBPyConnection:
    """Получить соединение с DuckDB (создаёт файл при первом вызове)."""
    conn = duckdb.connect(str(DB_PATH))
    _init_schema(conn)
    return conn


def _init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Создать схему таблиц при первом запуске."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_events (
            task_id VARCHAR NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            changed_value VARCHAR NOT NULL,
            added_values VARCHAR,
            removed_values VARCHAR,
            author_full_name VARCHAR,
            activity_type VARCHAR,
            source_file VARCHAR NOT NULL,
            file_hash VARCHAR NOT NULL,
            row_hash VARCHAR NOT NULL,
            loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (row_hash)
        )
    """)
    # Индексы для быстрых аналитических запросов
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_events_task_ts ON task_events(task_id, timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_events_file_hash ON task_events(file_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_events_changed ON task_events(changed_value)")


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
    conn = get_conn()
    result = conn.execute(
        "SELECT 1 FROM task_events WHERE file_hash = ? LIMIT 1", (file_hash,)
    ).fetchone()
    return result is not None


def load_dataframe_to_db(df: pd.DataFrame, source_file: str, file_hash: str) -> int:
    """
    Загрузить DataFrame в DuckDB с дедупликацией по row_hash.
    Возвращает количество реально добавленных строк.
    """
    if df.empty:
        return 0

    # Копия чтобы не менять оригинал
    df = df.copy()

    # Нормализация названий колонок
    if "task_identifier" in df.columns:
        df["task_id"] = df["task_identifier"]
    elif "issue_id" in df.columns:
        df["task_id"] = df["issue_id"]
    elif "iissue_id" in df.columns:
        df["task_id"] = df["iissue_id"]

    # row_hash для каждой строки
    df["row_hash"] = df.apply(make_row_hash, axis=1)

    # Метаданные файла
    df["source_file"] = source_file
    df["file_hash"] = file_hash

    # Приведение timestamp к TIMESTAMP
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    # Добавляем activity_type если нет
    if "activity_type" not in df.columns:
        df["activity_type"] = ""

    # Выбор нужных колонок
    cols = [
        "task_id", "timestamp", "changed_value", "added_values",
        "removed_values", "author_full_name", "activity_type",
        "source_file", "file_hash", "row_hash"
    ]
    df = df[cols].dropna(subset=["task_id", "timestamp", "changed_value"])

    if df.empty:
        return 0

    conn = get_conn()

    # INSERT OR IGNORE — пропускает дубликаты по PRIMARY KEY (row_hash)
    result = conn.execute("""
        INSERT OR IGNORE INTO task_events 
        (task_id, timestamp, changed_value, added_values, removed_values,
         author_full_name, activity_type, source_file, file_hash, row_hash)
        SELECT task_id, timestamp, changed_value, added_values, removed_values,
               author_full_name, activity_type, source_file, file_hash, row_hash
        FROM df
    """)
    # DuckDB возвращает количество вставленных строк через fetchall()[0][0]
    count_result = result.fetchall()
    if count_result and len(count_result) > 0 and len(count_result[0]) > 0:
        return count_result[0][0]
    return 0


def get_db_fingerprint() -> str:
    """Короткий отпечаток содержимого БД для ключа кэша pipeline."""
    conn = get_conn()
    row = conn.execute("""
        SELECT COALESCE(COUNT(*), 0) || '|' ||
               COALESCE(CAST(MAX(loaded_at) AS VARCHAR), '') || '|' ||
               COALESCE(CAST(MAX(timestamp) AS VARCHAR), '')
        FROM task_events
    """).fetchone()
    return str(row[0]) if row else "empty"


def get_all_events() -> pd.DataFrame:
    """Получить все события для аналитики."""
    conn = get_conn()
    return conn.execute("SELECT * FROM task_events ORDER BY task_id, timestamp").df()


def get_events_for_tasks(task_ids: list[str]) -> pd.DataFrame:
    """Получить события для списка задач."""
    if not task_ids:
        return pd.DataFrame()
    conn = get_conn()
    placeholders = ",".join(["?"] * len(task_ids))
    return conn.execute(
        f"SELECT * FROM task_events WHERE task_id IN ({placeholders}) ORDER BY task_id, timestamp",
        task_ids
    ).df()


def get_summary_stats() -> dict:
    """Базовая статистика по БД."""
    conn = get_conn()
    stats = conn.execute("""
        SELECT 
            COUNT(*) as total_rows,
            COUNT(DISTINCT task_id) as unique_tasks,
            COUNT(DISTINCT source_file) as loaded_files,
            MIN(timestamp) as earliest_event,
            MAX(timestamp) as latest_event,
            MAX(loaded_at) as last_load
        FROM task_events
    """).fetchone()
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
    conn = get_conn()
    conn.execute("DELETE FROM task_events")
    conn.execute("VACUUM")