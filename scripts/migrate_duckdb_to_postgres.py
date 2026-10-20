#!/usr/bin/env python3
"""Разовая миграция task_events из legacy DuckDB в PostgreSQL.

Перед запуском остановите приложение и сделайте резервную копию файла DuckDB.
Требуется отдельно установленный пакет duckdb:
    python -m pip install duckdb
"""
import argparse
import io
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema.sql"
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
TEXT_COLUMNS = [
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duckdb", required=True, help="Путь к analytics.duckdb")
    parser.add_argument(
        "--dsn",
        default=os.getenv("ANALYTICS_DATABASE_URL"),
        help="DSN PostgreSQL (по умолчанию ANALYTICS_DATABASE_URL)",
    )
    return parser.parse_args()


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    now = pd.Timestamp.now()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["loaded_at"] = pd.to_datetime(df["loaded_at"], errors="coerce").fillna(now)
    if getattr(df["timestamp"].dt, "tz", None) is not None:
        df["timestamp"] = df["timestamp"].dt.tz_localize(None)
    if getattr(df["loaded_at"].dt, "tz", None) is not None:
        df["loaded_at"] = df["loaded_at"].dt.tz_localize(None)
    df["timestamp"] = [value.to_pydatetime() for value in df["timestamp"]]
    df["loaded_at"] = [value.to_pydatetime() for value in df["loaded_at"]]
    for column in TEXT_COLUMNS:
        df[column] = df[column].map(lambda value: None if pd.isna(value) else str(value))
    return df


def main() -> int:
    args = parse_args()
    if not args.dsn:
        print("Не задан --dsn или ANALYTICS_DATABASE_URL", file=sys.stderr)
        return 2
    duckdb_path = Path(args.duckdb).expanduser()
    if not duckdb_path.is_file():
        print(f"Файл не найден: {duckdb_path}", file=sys.stderr)
        return 2
    try:
        import duckdb
    except ImportError:
        print("Установите duckdb: python -m pip install duckdb", file=sys.stderr)
        return 2

    source = duckdb.connect(str(duckdb_path), read_only=True)
    source_count = source.execute("SELECT COUNT(*) FROM task_events").fetchone()[0]
    if not source_count:
        print("В DuckDB нет событий — миграция не требуется.")
        return 0
    column_sql = ", ".join(
        f'"{column}"' if column == "timestamp" else column
        for column in EVENT_COLUMNS
    )
    df = source.execute(
        f'SELECT {column_sql}, loaded_at FROM task_events '
        'ORDER BY task_id, "timestamp"'
    ).fetchdf()
    source.close()
    df = normalize(df)

    statements = [
        statement.strip()
        for statement in SCHEMA_PATH.read_text(encoding="utf-8").split(";")
        if statement.strip()
    ]
    with psycopg.connect(args.dsn) as conn:
        with conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)
            before = cur.execute("SELECT COUNT(*) FROM task_events").fetchone()[0]
            cur.execute(
                "CREATE TEMP TABLE _task_events_staging ON COMMIT DROP "
                "AS SELECT * FROM task_events WITH NO DATA"
            )
            copy_columns = column_sql + ", loaded_at"
            buffer = io.StringIO()
            df[EVENT_COLUMNS + ["loaded_at"]].to_csv(
                buffer, index=False, header=False, lineterminator="\n", na_rep="\\N"
            )
            buffer.seek(0)
            with cur.copy(
                f"COPY _task_events_staging ({copy_columns}) "
                "FROM STDIN WITH (FORMAT csv, NULL '\\N')"
            ) as copy:
                while chunk := buffer.read(1024 * 1024):
                    copy.write(chunk)
            cur.execute(
                f"""
                INSERT INTO task_events ({copy_columns})
                SELECT {copy_columns} FROM _task_events_staging
                ON CONFLICT (row_hash) DO NOTHING
                RETURNING 1
                """
            )
            inserted = len(cur.fetchall())
            total = cur.execute("SELECT COUNT(*) FROM task_events").fetchone()[0]

    print(f"Строк в DuckDB: {source_count}")
    print(f"Строк в PostgreSQL до миграции: {before}")
    print(f"Добавлено: {inserted}")
    print(f"Строк в PostgreSQL после миграции: {total}")
    if before == 0 and total != source_count:
        print("ОШИБКА: количество строк не совпадает", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
