from typing import Dict, List, Optional
import numpy as np
import pandas as pd
import logging

from src.models.activity import IssueTimeline
from src.models.metrics import (
    AggregationResult,
    StageTimeMetrics,
    LeadCycleMetrics,
    calculate_aggregations,
    hours_to_days,
)

logger = logging.getLogger(__name__)


def calculate_all_metrics(timelines: Dict[str, IssueTimeline]) -> Dict:
    lead_times = []
    cycle_times = []
    stage_times = {"analytics": [], "development": [], "testing": []}

    for issue_id, timeline in timelines.items():
        lt = calculate_lead_time(timeline)
        if lt is not None:
            lead_times.append(lt)

        ct = calculate_cycle_time(timeline)
        if ct is not None:
            cycle_times.append(ct)

        for stage in ["analytics", "development", "testing"]:
            stage_time = calculate_stage_time_total(timeline, stage)
            if stage_time > 0:
                stage_times[stage].append(stage_time)

    return {
        "lead_time": calculate_aggregations(lead_times),
        "cycle_time": calculate_aggregations(cycle_times),
        "stage_times": {
            stage: calculate_aggregations(times)
            for stage, times in stage_times.items()
        },
    }


def calculate_lead_time(timeline: IssueTimeline) -> Optional[float]:
    from src.processors.timeline_builder import calculate_lead_time as tl_lead_time
    return tl_lead_time(timeline)


def calculate_cycle_time(timeline: IssueTimeline) -> Optional[float]:
    from src.processors.timeline_builder import calculate_cycle_time as tl_cycle_time
    return tl_cycle_time(timeline)


def calculate_stage_time_total(timeline: IssueTimeline, stage: str) -> float:
    from src.processors.timeline_builder import calculate_stage_time
    return calculate_stage_time(timeline, stage)


def calculate_worklog_metrics(
    timelines: Dict[str, IssueTimeline]
) -> Dict:
    from collections import defaultdict

    by_author = defaultdict(lambda: {"total_hours": 0.0, "by_type": defaultdict(float), "by_month": defaultdict(float)})
    by_month = defaultdict(lambda: {"hours": 0.0, "issues": set()})
    by_quarter = defaultdict(lambda: {"hours": 0.0, "issues": set()})

    for timeline in timelines.values():
        for work in timeline.work_items:
            author = work.author or "Unknown"
            hours = work.duration_hours
            work_type = work.work_type
            date = work.date

            by_author[author]["total_hours"] += hours
            by_author[author]["by_type"][work_type] += hours

            month_key = date.strftime("%Y-%m")
            by_author[author]["by_month"][month_key] += hours

            by_month[month_key]["hours"] += hours
            by_month[month_key]["issues"].add(timeline.issue_id)

            quarter = (date.month - 1) // 3 + 1
            quarter_key = f"{date.year}-Q{quarter}"
            by_quarter[quarter_key]["hours"] += hours
            by_quarter[quarter_key]["issues"].add(timeline.issue_id)

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
    }


def calculate_distributions(timelines: Dict[str, IssueTimeline], df: pd.DataFrame) -> Dict:
    distributions = {
        "by_status": {},
        "by_author": {},
        "by_type": {},
        "by_priority": {},
        "by_sprint": {},
    }

    for timeline in timelines.values():
        if timeline.transitions:
            last_status = timeline.transitions[-1].to_status
            distributions["by_status"][last_status] = distributions["by_status"].get(last_status, 0) + 1

    # Get author distribution from work items
    for timeline in timelines.values():
        for work in timeline.work_items:
            author = work.author or "Unknown"
            distributions["by_author"][author] = distributions["by_author"].get(author, 0) + 1

    return distributions


def calculate_trends(timelines: Dict[str, IssueTimeline]) -> Dict:
    weekly_data = {}
    monthly_data = {}

    for timeline in timelines.values():
        if not timeline.completed_at:
            continue

        week_key = timeline.completed_at.strftime("%Y-W%U")
        month_key = timeline.completed_at.strftime("%Y-%m")

        lt = calculate_lead_time(timeline)
        ct = calculate_cycle_time(timeline)

        for period_key, period_data in [(week_key, weekly_data), (month_key, monthly_data)]:
            if period_key not in period_data:
                period_data[period_key] = {"lead_times": [], "cycle_times": [], "count": 0}
            if lt:
                period_data[period_key]["lead_times"].append(lt)
            if ct:
                period_data[period_key]["cycle_times"].append(ct)
            period_data[period_key]["count"] += 1

    def process_period(period_data):
        result = []
        for period in sorted(period_data.keys()):
            data = period_data[period]
            result.append({
                "period": period,
                "avg_lead_time": np.mean(data["lead_times"]) if data["lead_times"] else 0,
                "avg_cycle_time": np.mean(data["cycle_times"]) if data["cycle_times"] else 0,
                "issues_count": data["count"],
            })
        return result

    return {
        "by_week": process_period(weekly_data),
        "by_month": process_period(monthly_data),
    }


def calculate_rework_count(timelines: Dict[str, IssueTimeline]) -> int:
    rework_count = 0
    for timeline in timelines.values():
        for i in range(1, len(timeline.transitions)):
            prev_to = timeline.transitions[i - 1].to_status
            curr_from = timeline.transitions[i].from_status
            if prev_to in {"В тестировании", "Протестировано"} and curr_from in {"В разработке", "К разработке"}:
                rework_count += 1
    return rework_count


def calculate_avg_transitions(timelines: Dict[str, IssueTimeline]) -> float:
    if not timelines:
        return 0
    total = sum(len(t.transitions) for t in timelines.values())
    return total / len(timelines)