import pandas as pd
import ast
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from src.config import DATA_DIR, MAX_FILE_SIZE_MB, ALLOWED_EXTENSIONS

logger = logging.getLogger(__name__)


def validate_file(file_path: Path) -> bool:
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if file_path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file format: {file_path.suffix}")

    size_mb = file_path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise ValueError(f"File too large: {size_mb:.1f}MB > {MAX_FILE_SIZE_MB}MB")

    return True


def safe_parse(value: str) -> Any:
    if pd.isna(value) or value == "" or value == "[]":
        return []

    value = value.strip()
    if not value:
        return []

    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            try:
                cleaned = value.replace("'", '"').replace('\\"', '"')
                return json.loads(cleaned)
            except:
                logger.warning(f"Failed to parse value: {value[:100]}")
                return []


def parse_work_item(added_values: list) -> Optional[Dict]:
    if not added_values or len(added_values) == 0:
        return None

    try:
        work_str = added_values[0]
        if isinstance(work_str, str):
            work_str = work_str.replace('\\"', '"')
            if "{" in work_str:
                json_str = work_str[work_str.find("{") : work_str.rfind("}") + 1]
                return json.loads(json_str)
    except Exception as e:
        logger.warning(f"Failed to parse work item: {e}")

    return None


def load_and_parse_csv(file_path: Optional[str] = None) -> pd.DataFrame:
    if file_path is None:
        file_path = DATA_DIR / "input.csv"
    else:
        file_path = Path(file_path)

    validate_file(file_path)

    logger.info(f"Loading CSV from: {file_path}")

    df = pd.read_csv(
        file_path,
        encoding="utf-8-sig",
        dtype=str,
    )

    logger.info(f"Loaded {len(df)} rows")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")

    df["parsed_added"] = df["added_values"].apply(safe_parse)
    df["parsed_removed"] = df["removed_values"].apply(safe_parse)

    df["status_change"] = df.apply(
        lambda row: {
            "field": row["changed_value"],
            "added": row["parsed_added"],
            "removed": row["parsed_removed"],
        }
        if row["activity_type"] == "CustomFieldActivityItem"
        else None,
        axis=1,
    )

    df["work_item"] = df.apply(
        lambda row: parse_work_item(row["parsed_added"])
        if row["activity_type"] == "WorkItemActivityItem"
        else None,
        axis=1,
    )

    df["author"] = df["author"].fillna("").str.strip()
    df["author_full_name"] = df["author_full_name"].fillna("").str.strip()

    invalid_dates = df["timestamp"].isna().sum()
    if invalid_dates > 0:
        logger.warning(f"Found {invalid_dates} rows with invalid timestamps")

    return df


def get_status_transitions(df: pd.DataFrame) -> pd.DataFrame:
    status_changes = df[
        (df["activity_type"] == "CustomFieldActivityItem")
        & (df["changed_value"] == "State")
    ].copy()

    status_changes = status_changes.sort_values(["issue_id", "timestamp"])

    return status_changes


def get_work_items(df: pd.DataFrame) -> pd.DataFrame:
    work_items = df[df["activity_type"] == "WorkItemActivityItem"].copy()
    return work_items


def get_unique_issues(df: pd.DataFrame) -> List[str]:
    return df["issue_id"].dropna().unique().tolist()


def get_date_range(df: pd.DataFrame) -> tuple:
    min_date = df["timestamp"].min()
    max_date = df["timestamp"].max()
    return min_date, max_date