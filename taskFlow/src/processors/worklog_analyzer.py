from typing import Dict, List, Any
from collections import defaultdict
import pandas as pd
import logging

from src.data_loader import get_work_items
from src.models.activity import WorkItem
from src.utils.calendar_utils import calculate_working_hours

logger = logging.getLogger(__name__)


def analyze_worklog(df: pd.DataFrame) -> Dict:
    work_items = get_work_items(df)

    by_author = defaultdict(lambda: {
        "total_hours": 0.0,
        "by_type": defaultdict(float),
        "by_month": defaultdict(float),
    })
    by_month = defaultdict(lambda: {"hours": 0.0, "issues": set()})
    by_quarter = defaultdict(lambda: {"hours": 0.0, "issues": set()})
    by_type = defaultdict(float)
    by_issue = defaultdict(float)

    for _, row in work_items.iterrows():
        work = row["work_item"]
        if not work:
            continue

        try:
            author = row.get("author_full_name") or row.get("author", "Unknown")
            duration_minutes = work.get("duration", 0)
            duration_hours = duration_minutes / 60

            if duration_hours <= 0:
                continue

            work_type = work.get("type", "Прочее")
            date_ms = work.get("date")

            if date_ms:
                work_date = pd.to_datetime(date_ms, unit="ms")
            else:
                work_date = pd.to_datetime(row["timestamp"])

            issue_id = row["issue_id"]

            by_author[author]["total_hours"] += duration_hours
            by_author[author]["by_type"][work_type] += duration_hours

            month_key = work_date.strftime("%Y-%m")
            by_author[author]["by_month"][month_key] += duration_hours

            by_month[month_key]["hours"] += duration_hours
            by_month[month_key]["issues"].add(issue_id)

            quarter = (work_date.month - 1) // 3 + 1
            quarter_key = f"{work_date.year}-Q{quarter}"
            by_quarter[quarter_key]["hours"] += duration_hours
            by_quarter[quarter_key]["issues"].add(issue_id)

            by_type[work_type] += duration_hours
            by_issue[issue_id] += duration_hours

        except Exception as e:
            logger.warning(f"Error processing work item: {e}")

    for author in by_author:
        by_author[author]["by_type"] = dict(by_author[author]["by_type"])
        by_author[author]["by_month"] = dict(by_author[author]["by_month"])

    for month in by_month:
        by_month[month]["issues"] = len(by_month[month]["issues"])

    for quarter in by_quarter:
        by_quarter[quarter]["issues"] = len(by_quarter[quarter]["issues"])

    return {
        "by_author": dict(by_author),
        "by_month": dict(by_month),
        "by_quarter": dict(by_quarter),
        "by_type": dict(by_type),
        "by_issue": dict(by_issue),
        "total_hours": sum(by_type.values()),
    }


def get_author_worklog(df: pd.DataFrame, author: str) -> List[Dict]:
    work_items = get_work_items(df)
    author_work = work_items[
        (work_items["author"] == author) | (work_items["author_full_name"] == author)
    ]

    result = []
    for _, row in author_work.iterrows():
        work = row["work_item"]
        if not work:
            continue

        duration_minutes = work.get("duration", 0)
        duration_hours = duration_minutes / 60

        if duration_hours <= 0:
            continue

        date_ms = work.get("date")
        if date_ms:
            work_date = pd.to_datetime(date_ms, unit="ms")
        else:
            work_date = pd.to_datetime(row["timestamp"])

        result.append({
            "issue_id": row["issue_id"],
            "work_type": work.get("type", "Прочее"),
            "duration_hours": duration_hours,
            "date": work_date,
            "text": work.get("text"),
        })

    return result


def get_worklog_by_type(df: pd.DataFrame) -> Dict[str, float]:
    work_items = get_work_items(df)
    by_type = defaultdict(float)

    for _, row in work_items.iterrows():
        work = row["work_item"]
        if not work:
            continue

        duration_minutes = work.get("duration", 0)
        duration_hours = duration_minutes / 60

        if duration_hours <= 0:
            continue

        work_type = work.get("type", "Прочее")
        by_type[work_type] += duration_hours

    return dict(by_type)


def get_worklog_by_period(df: pd.DataFrame, period: str = "month") -> Dict[str, Dict]:
    work_items = get_work_items(df)
    result = defaultdict(lambda: {"hours": 0.0, "issues": set()})

    for _, row in work_items.iterrows():
        work = row["work_item"]
        if not work:
            continue

        duration_minutes = work.get("duration", 0)
        duration_hours = duration_minutes / 60

        if duration_hours <= 0:
            continue

        date_ms = work.get("date")
        if date_ms:
            work_date = pd.to_datetime(date_ms, unit="ms")
        else:
            work_date = pd.to_datetime(row["timestamp"])

        if period == "month":
            key = work_date.strftime("%Y-%m")
        elif period == "quarter":
            quarter = (work_date.month - 1) // 3 + 1
            key = f"{work_date.year}-Q{quarter}"
        elif period == "week":
            key = work_date.strftime("%Y-W%U")
        else:
            key = work_date.strftime("%Y-%m")

        result[key]["hours"] += duration_hours
        result[key]["issues"].add(row["issue_id"])

    for key in result:
        result[key]["issues"] = len(result[key]["issues"])

    return dict(result)