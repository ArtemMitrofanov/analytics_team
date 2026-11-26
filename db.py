"""db.py — PostgreSQL хранение событий задач с дедупликацией по row_hash."""
import hashlib
import io
import os
import re
import threading
from contextlib import contextmanager
from dataclasses import replace
from datetime import date
from pathlib import Path
from uuid import uuid4

from config import DEFAULT_TEAM_ID, TEAMS, Team, team_display_label
from data.team_import import WrongTeamImport, check_import_subsystem

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
        with target.connection() as conn:
            conn.execute(
                "SELECT pg_advisory_xact_lock("
                "hashtext('team_process_analytics_schema')::bigint)"
            )
            conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
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


def is_file_loaded(file_hash: str, *, team_id: str = DEFAULT_TEAM_ID) -> bool:
    """Проверить, загружен ли файл с таким хэшем."""
    with _connection() as conn:
        row = conn.execute(
            "SELECT EXISTS(SELECT 1 FROM task_events WHERE team_id = %s AND file_hash = %s)",
            (team_id, file_hash),
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


def _get_teams(conn) -> dict[str, Team]:
    rows = conn.execute(
        "SELECT team_id, name, project, subsystem FROM web_teams ORDER BY lower(name), team_id"
    ).fetchall()
    overrides = dict(conn.execute(
        "SELECT team_id, display_name FROM configured_team_overrides",
    ).fetchall())
    configured_teams = {
        team_id: replace(team, display_name=overrides.get(team_id))
        for team_id, team in TEAMS.items()
        if team_id not in overrides or overrides[team_id] is not None
    }
    return configured_teams | {
        team_id: Team(name, project=project, subsystem=subsystem)
        for team_id, name, project, subsystem in rows
    }


def get_teams() -> dict[str, Team]:
    with _connection() as conn:
        return _get_teams(conn)


def _lock_team_registry(conn) -> None:
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('analytics_team_import_name')::bigint)")


def _require_team_admin(username: str) -> None:
    from access_control import get_user_role

    if get_user_role(username) != "admin":
        raise PermissionError("Управлять командами может только администратор.")


def create_team(username: str, name: str, project: str, subsystem: str = "") -> str:
    """Создать команду от имени вошедшего администратора."""
    _require_team_admin(username)
    name, project, subsystem = name.strip(), project.strip(), subsystem.strip()
    if not re.fullmatch(r"[\w.]+(?:-[\w.]+)*", project):
        raise ValueError("Укажите префикс issue_id, например Finance или KBA-Budg.")
    if len(project) > 100 or len(name) > 100 or len(subsystem) > 200:
        raise ValueError("Название и префикс должны быть до 100 символов, подсистема — до 200.")

    if not name:
        suggested_team = Team(project, project=project, subsystem=subsystem)
        name = team_display_label(suggested_team)

    with _connection() as conn:
        _lock_team_registry(conn)
        teams = _get_teams(conn)
        saved_projects = dict(conn.execute("SELECT team_id, name FROM team_display_names").fetchall())
        identity = (project.casefold(), subsystem.casefold())
        for team_id, team in teams.items():
            existing_project = team.project or saved_projects.get(team_id, "")
            if (existing_project.casefold(), team.subsystem.casefold()) == identity:
                display_name = team_display_label(team, existing_project) if team_id in TEAMS else team.name
                raise ValueError(f"Команда с таким префиксом и подсистемой уже существует: «{display_name}».")

        team_id = f"web-{uuid4().hex}"
        conn.execute(
            "INSERT INTO web_teams (team_id, name, project, subsystem) VALUES (%s, %s, %s, %s)",
            (team_id, name, project, subsystem),
        )
        return team_id


def rename_team(username: str, team_id: str, name: str) -> None:
    _require_team_admin(username)
    name = name.strip()
    if not 1 <= len(name) <= 100:
        raise ValueError("Укажите название длиной от 1 до 100 символов.")

    with _connection() as conn:
        _lock_team_registry(conn)
        if team_id not in _get_teams(conn):
            raise ValueError("Команда уже удалена.")
        if team_id in TEAMS:
            conn.execute(
                """
                INSERT INTO configured_team_overrides (team_id, display_name) VALUES (%s, %s)
                ON CONFLICT (team_id) DO UPDATE SET display_name = EXCLUDED.display_name
                """,
                (team_id, name),
            )
        else:
            conn.execute("UPDATE web_teams SET name = %s WHERE team_id = %s", (name, team_id))


def delete_team(username: str, team_id: str) -> int:
    """Удалить команду и все её события в одной транзакции."""
    _require_team_admin(username)
    with _connection() as conn:
        _lock_team_registry(conn)
        if team_id not in _get_teams(conn):
            raise ValueError("Команда уже удалена.")
        deleted = conn.execute("DELETE FROM task_events WHERE team_id = %s", (team_id,)).rowcount
        conn.execute("DELETE FROM team_display_names WHERE team_id = %s", (team_id,))
        if team_id in TEAMS:
            conn.execute(
                """
                INSERT INTO configured_team_overrides (team_id, display_name) VALUES (%s, NULL)
                ON CONFLICT (team_id) DO UPDATE SET display_name = NULL
                """,
                (team_id,),
            )
        else:
            conn.execute("DELETE FROM web_teams WHERE team_id = %s", (team_id,))
        return deleted


def _check_import_team(conn, team_id: str, team_name: str, teams: dict[str, Team]) -> None:
    team_names = dict(conn.execute(
        "SELECT team_id, name FROM team_display_names "
        "WHERE team_id = %s OR (name = %s AND NOT (team_id = ANY(%s)))",
        (team_id, team_name, [key for key, team in teams.items() if team.subsystem]),
    ).fetchall())
    team_names.update({
        key: team.project for key, team in teams.items()
        if not team.subsystem and team.project and (key == team_id or team.project == team_name)
    })
    expected_name = team_names.get(team_id)
    if expected_name is not None and team_name != expected_name:
        raise WrongTeamImport(
            f"Файл относится к команде «{team_name}», выбрана «{expected_name}». "
            "Строки из файла не загружены."
        )
    if expected_name is None and team_name in team_names.values():
        raise WrongTeamImport(
            f"Префикс «{team_name}» уже принадлежит другой команде. Строки из файла не загружены."
        )


def load_dataframe_to_db(
    df: pd.DataFrame, source_file: str, file_hash: str, *,
    team_id: str = DEFAULT_TEAM_ID, team_name: str | None = None,
) -> int:
    """
    Загрузить DataFrame в PostgreSQL с дедупликацией по row_hash.
    Возвращает количество реально добавленных строк.
    """
    if df.empty:
        return 0

    source_frame = df
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
    df["team_id"] = team_id
    copy_columns = [*EVENT_COLUMNS, "team_id"]
    column_sql = ", ".join(
        f'"{column}"' if column == "timestamp" else column for column in copy_columns
    )

    with _connection() as conn:
        _lock_team_registry(conn)
        teams = _get_teams(conn)
        if team_id not in teams and (team_id in TEAMS or team_id.startswith("web-")):
            raise WrongTeamImport("Команда уже удалена. Строки из файла не загружены.")
        scoped_team = check_import_subsystem(source_frame, team_id, team_name, teams)
        if team_name is not None and not scoped_team:
            _check_import_team(conn, team_id, team_name, teams)
        conn.execute(
            "CREATE TEMP TABLE _task_events_staging ON COMMIT DROP "
            "AS SELECT * FROM task_events WITH NO DATA"
        )
        buffer = io.StringIO()
        df[copy_columns].to_csv(
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
                ON CONFLICT (team_id, row_hash) DO NOTHING
                RETURNING 1
                """
            )
            inserted = len(cur.fetchall())
            if inserted and team_name is not None and not scoped_team:
                cur.execute(
                    """
                    INSERT INTO team_display_names (team_id, name) VALUES (%s, %s)
                    ON CONFLICT (team_id) DO NOTHING
                    """,
                    (team_id, team_name),
                )
            return inserted


def get_team_display_names(team_ids: list[str]) -> dict[str, str]:
    with _connection() as conn:
        rows = conn.execute(
            "SELECT team_id, name FROM team_display_names WHERE team_id = ANY(%s)",
            (team_ids,),
        ).fetchall()
    return dict(rows)


def get_db_fingerprint(*, team_id: str = DEFAULT_TEAM_ID) -> str:
    """Короткий отпечаток содержимого БД для ключа кэша pipeline."""
    with _connection() as conn:
        row = conn.execute(
            'SELECT COUNT(*), MAX(loaded_at), MAX("timestamp") FROM task_events WHERE team_id = %s',
            (team_id,),
        ).fetchone()
    if not row:
        return "empty"
    return f"{row[0]}|{row[1] or ''}|{row[2] or ''}"


def get_all_events(*, team_id: str = DEFAULT_TEAM_ID) -> pd.DataFrame:
    """Получить все события для аналитики."""
    with _connection() as conn:
        return _read_df(
            conn,
            'SELECT * FROM task_events WHERE team_id = %s ORDER BY task_id, "timestamp"',
            (team_id,),
        )


def get_event_months(*, team_id: str = DEFAULT_TEAM_ID) -> list[date]:
    """Вернуть начала месяцев, в которых были события."""
    with _connection() as conn:
        rows = conn.execute(
            """SELECT DISTINCT date_trunc('month', "timestamp")::date AS month
               FROM task_events WHERE team_id = %s
               ORDER BY month""",
            (team_id,),
        ).fetchall()
    return [month for (month,) in rows]


def get_events_for_tasks(task_ids: list[str], *, team_id: str = DEFAULT_TEAM_ID) -> pd.DataFrame:
    """Получить события для списка задач."""
    if not task_ids:
        return _normalize_event_dtypes(
            pd.DataFrame(columns=EVENT_COLUMNS + ["team_id", "loaded_at"])
        )
    with _connection() as conn:
        return _read_df(
            conn,
            'SELECT * FROM task_events '
            'WHERE team_id = %s AND task_id = ANY(%s) ORDER BY task_id, "timestamp"',
            (team_id, [str(task_id) for task_id in task_ids]),
        )


def get_summary_stats(*, team_id: str = DEFAULT_TEAM_ID) -> dict:
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
            FROM task_events WHERE team_id = %s
            """,
            (team_id,),
        ).fetchone()
    return {
        "total_rows": stats[0],
        "unique_tasks": stats[1],
        "loaded_files": stats[2],
        "earliest_event": stats[3],
        "latest_event": stats[4],
        "last_load": stats[5],
    }


def clear_database(*, team_id: str = DEFAULT_TEAM_ID) -> None:
    """Удалить события выбранной команды."""
    with _connection() as conn:
        conn.execute("DELETE FROM task_events WHERE team_id = %s", (team_id,))
