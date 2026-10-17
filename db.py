"""db.py — DuckDB хранение событий задач с дедупликацией по row_hash."""
import hashlib
import os
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

DB_PATH = Path(os.getenv("DUCKDB_PATH", Path(__file__).resolve().parent / "data" / "analytics.duckdb"))


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

    # --- Граф взаимодействий -------------------------------------------------
    # Сырые рёбра (период-независимые).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS graph_edges (
            edge_hash VARCHAR NOT NULL,
            issue_id VARCHAR,
            from_actor VARCHAR,
            from_role VARCHAR,
            to_actor VARCHAR,
            to_role VARCHAR,
            edge_type VARCHAR,
            stage VARCHAR,
            wait_min DOUBLE,
            resulted_in_rework BOOLEAN,
            deadline_slip BOOLEAN,
            ts_from TIMESTAMP,
            ts_to TIMESTAMP,
            PRIMARY KEY (edge_hash)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_graph_edges_type_stage ON graph_edges(edge_type, stage)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_graph_edges_roles ON graph_edges(from_role, to_role)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_graph_edges_issue ON graph_edges(issue_id)")

    # Агрегат (период-зависимый).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS graph_edges_agg (
            agg_hash VARCHAR NOT NULL,
            from_actor VARCHAR,
            from_role VARCHAR,
            to_actor VARCHAR,
            to_role VARCHAR,
            edge_type VARCHAR,
            stage VARCHAR,
            period_months INTEGER,
            cnt INTEGER,
            handoff_count INTEGER,
            rework_count INTEGER,
            wait_min_median DOUBLE,
            rework_rate DOUBLE,
            deadline_slip_rate DOUBLE,
            computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (agg_hash)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_graph_edges_agg_roles ON graph_edges_agg(from_role, to_role, period_months)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_graph_edges_agg_type_stage ON graph_edges_agg(edge_type, stage, period_months)")

    # Служебные метаданные (fingerprints, флаг устаревания).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS graph_meta (
            key VARCHAR NOT NULL,
            value VARCHAR,
            computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (key)
        )
    """)


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
    inserted = 0
    if count_result and len(count_result) > 0 and len(count_result[0]) > 0:
        inserted = int(count_result[0][0])
    if inserted > 0:
        # Новые события → граф взаимодействий устарел (пересборка ленивая).
        invalidate_graph()
    return inserted


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
    clear_graph_edges()


# --- Граф взаимодействий: таблицы, пересборка, fingerprints -----------------

GRAPH_EDGE_COLUMNS = [
    "edge_hash", "issue_id", "from_actor", "from_role", "to_actor", "to_role",
    "edge_type", "stage", "wait_min", "resulted_in_rework", "deadline_slip",
    "ts_from", "ts_to",
]

GRAPH_AGG_COLUMNS = [
    "agg_hash", "from_actor", "from_role", "to_actor", "to_role", "edge_type",
    "stage", "period_months", "cnt", "handoff_count", "rework_count",
    "wait_min_median", "rework_rate", "deadline_slip_rate",
]


def upsert_graph_edges(edges_df: pd.DataFrame) -> int:
    """Вставить/обновить сырые рёбра графа (PK edge_hash). Возвращает число строк."""
    if edges_df is None or edges_df.empty:
        return 0
    df = edges_df.copy()
    for col in GRAPH_EDGE_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[GRAPH_EDGE_COLUMNS]
    df["ts_from"] = pd.to_datetime(df["ts_from"], errors="coerce")
    df["ts_to"] = pd.to_datetime(df["ts_to"], errors="coerce")

    conn = get_conn()
    conn.register("df_graph_edges", df)
    conn.execute("""
        INSERT OR REPLACE INTO graph_edges
        (edge_hash, issue_id, from_actor, from_role, to_actor, to_role,
         edge_type, stage, wait_min, resulted_in_rework, deadline_slip,
         ts_from, ts_to)
        SELECT edge_hash, issue_id, from_actor, from_role, to_actor, to_role,
               edge_type, stage, wait_min, resulted_in_rework, deadline_slip,
               ts_from, ts_to
        FROM df_graph_edges
    """)
    conn.unregister("df_graph_edges")
    return len(df)


def upsert_graph_edges_agg(agg_df: pd.DataFrame) -> int:
    """Вставить/обновить агрегат графа (PK agg_hash). Возвращает число строк."""
    if agg_df is None or agg_df.empty:
        return 0
    df = agg_df.copy()
    for col in GRAPH_AGG_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[GRAPH_AGG_COLUMNS]

    conn = get_conn()
    conn.register("df_graph_agg", df)
    conn.execute("""
        INSERT OR REPLACE INTO graph_edges_agg
        (agg_hash, from_actor, from_role, to_actor, to_role, edge_type, stage,
         period_months, cnt, handoff_count, rework_count, wait_min_median,
         rework_rate, deadline_slip_rate)
        SELECT agg_hash, from_actor, from_role, to_actor, to_role, edge_type,
               stage, period_months, cnt, handoff_count, rework_count,
               wait_min_median, rework_rate, deadline_slip_rate
        FROM df_graph_agg
    """)
    conn.unregister("df_graph_agg")
    return len(df)


def clear_graph_edges() -> None:
    """Очистить обе таблицы графа и метаданные пересборки."""
    conn = get_conn()
    conn.execute("DELETE FROM graph_edges")
    conn.execute("DELETE FROM graph_edges_agg")
    conn.execute("DELETE FROM graph_meta")


def get_graph_edges() -> pd.DataFrame:
    """Все сырые рёбра графа."""
    conn = get_conn()
    return conn.execute("SELECT * FROM graph_edges").df()


def get_graph_edges_agg(period_months: int) -> pd.DataFrame:
    """Агрегат рёбер графа за период N месяцев."""
    conn = get_conn()
    return conn.execute(
        "SELECT * FROM graph_edges_agg WHERE period_months = ?", (int(period_months),)
    ).df()


def set_graph_meta(key: str, value: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO graph_meta (key, value, computed_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
        (key, str(value)),
    )


def get_graph_meta(key: str) -> Optional[str]:
    conn = get_conn()
    row = conn.execute("SELECT value FROM graph_meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def invalidate_graph() -> None:
    """Пометить граф устаревшим (пересборка выполнится лениво)."""
    set_graph_meta("dirty", "1")


def is_graph_dirty() -> bool:
    return get_graph_meta("dirty") == "1"


def get_graph_fingerprint() -> str:
    """sha256 набора file_hash в БД + содержимого config/team.json.

    Период в отпечаток НЕ входит: сырые рёбра от него не зависят.
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT file_hash FROM task_events ORDER BY file_hash"
    ).fetchall()
    payload = "|".join(str(r[0]) for r in rows)
    team_file = Path(__file__).resolve().parent / "config" / "team.json"
    team = team_file.read_text(encoding="utf-8") if team_file.exists() else ""
    return hashlib.sha256(f"{payload}||{team}".encode()).hexdigest()


def get_graph_agg_fingerprint(period_months: int) -> str:
    """Отпечаток агрегата: (graph_fingerprint, period_months)."""
    return hashlib.sha256(
        f"{get_graph_fingerprint()}|{int(period_months)}".encode()
    ).hexdigest()