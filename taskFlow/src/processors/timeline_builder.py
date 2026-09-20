from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import logging

import pandas as pd

from src.config import (
    ANALYTICS_STATUSES,
    DEVELOPMENT_STATUSES,
    TESTING_STATUSES,
    COMPLETION_STATUSES,
    STATUS_STAGE_MAP,
)
from src.utils.calendar_utils import calculate_working_hours
from src.models.activity import StatusTransition, IssueTimeline, WorkItem

logger = logging.getLogger(__name__)


def build_timelines(df: pd.DataFrame) -> Dict[str, IssueTimeline]:
    status_changes = df[
        (df["activity_type"] == "CustomFieldActivityItem")
        & (df["changed_value"] == "State")
    ].copy()

    status_changes = status_changes.sort_values(["issue_id", "timestamp"])

    timelines: Dict[str, IssueTimeline] = {}

    for issue_id, group in status_changes.groupby("issue_id"):
        timeline = IssueTimeline(issue_id=issue_id)
        prev_status = None
        prev_time = None
        prev_author = None

        for _, row in group.iterrows():
            added = row["parsed_added"]
            new_status = added[0] if added and len(added) > 0 else None

            if new_status is None:
                continue

            current_time = row["timestamp"]
            current_author = row.get("author_full_name") or row.get("author")

            if prev_status is not None and prev_time is not None:
                duration = calculate_working_hours(prev_time, current_time)

                if duration > 0:
                    transition = StatusTransition(
                        issue_id=issue_id,
                        from_status=prev_status,
                        to_status=new_status,
                        from_date=prev_time,
                        to_date=current_time,
                        duration_hours=duration,
                        duration_days=duration / 8,
                        author=prev_author,
                    )
                    timeline.transitions.append(transition)

            if timeline.created_at is None:
                timeline.created_at = current_time

            if new_status in COMPLETION_STATUSES:
                timeline.completed_at = current_time

            if (
                timeline.first_dev_at is None
                and new_status in DEVELOPMENT_STATUSES
                and prev_status not in DEVELOPMENT_STATUSES
            ):
                timeline.first_dev_at = current_time

            prev_status = new_status
            prev_time = current_time
            prev_author = current_author

        timelines[issue_id] = timeline

    work_items = df[df["activity_type"] == "WorkItemActivityItem"].copy()
    for _, row in work_items.iterrows():
        work = row["work_item"]
        if not work:
            continue

        issue_id = row["issue_id"]
        if issue_id not in timelines:
            timelines[issue_id] = IssueTimeline(issue_id=issue_id)

        try:
            duration_minutes = work.get("duration", 0)
            duration_hours = duration_minutes / 60

            date_ms = work.get("date")
            if date_ms:
                work_date = pd.to_datetime(date_ms, unit="ms")
            else:
                work_date = row["timestamp"]

            work_type = work.get("type", "Прочее")

            work_item = WorkItem(
                issue_id=issue_id,
                author=row.get("author_full_name") or row.get("author", ""),
                author_full_name=row.get("author_full_name"),
                work_type=work_type,
                duration_minutes=duration_minutes,
                duration_hours=duration_hours,
                date=work_date,
                text=work.get("text"),
                timestamp=row["timestamp"],
            )
            timelines[issue_id].work_items.append(work_item)
        except Exception as e:
            logger.warning(f"Failed to parse work item for {issue_id}: {e}")

    return timelines


def get_stage_for_status(status: str) -> Optional[str]:
    return STATUS_STAGE_MAP.get(status)


def is_analytics_status(status: str) -> bool:
    return status in ANALYTICS_STATUSES


def is_development_status(status: str) -> bool:
    return status in DEVELOPMENT_STATUSES


def is_testing_status(status: str) -> bool:
    return status in TESTING_STATUSES


def is_completion_status(status: str) -> bool:
    return status in COMPLETION_STATUSES


def calculate_stage_time(
    timeline: IssueTimeline, stage: str
) -> float:
    stage_statuses = {
        "analytics": ANALYTICS_STATUSES,
        "development": DEVELOPMENT_STATUSES,
        "testing": TESTING_STATUSES,
    }
    statuses = stage_statuses.get(stage, set())

    total = 0.0
    for transition in timeline.transitions:
        if transition.from_status in statuses or transition.to_status in statuses:
            total += transition.duration_hours

    return total


def calculate_lead_time(timeline: IssueTimeline) -> Optional[float]:
    if timeline.created_at and timeline.completed_at:
        return calculate_working_hours(timeline.created_at, timeline.completed_at)
    return None


def calculate_cycle_time(timeline: IssueTimeline) -> Optional[float]:
    if timeline.first_dev_at and timeline.completed_at:
        return calculate_working_hours(timeline.first_dev_at, timeline.completed_at)
    return None


def build_flow_data(timelines: Dict[str, IssueTimeline]) -> Tuple[List[Dict], List[Dict]]:
    nodes_set = set()
    links_dict = defaultdict(int)

    for timeline in timelines.values():
        for transition in timeline.transitions:
            nodes_set.add(transition.from_status)
            nodes_set.add(transition.to_status)
            links_dict[(transition.from_status, transition.to_status)] += 1

    nodes_list = sorted(list(nodes_set))
    node_map = {name: idx for idx, name in enumerate(nodes_list)}

    nodes = [{"id": idx, "name": name} for idx, name in enumerate(nodes_list)]
    links = [
        {"source": node_map[from_s], "target": node_map[to_s], "value": count}
        for (from_s, to_s), count in links_dict.items()
    ]

    return nodes, links