from datetime import datetime, time, timedelta
from typing import Tuple
import numpy as np

from src.config import (
    WORKING_HOURS_START,
    WORKING_HOURS_END,
    LUNCH_BREAK_START,
    LUNCH_BREAK_END,
    WORKING_DAYS,
)


def is_working_day(dt: datetime) -> bool:
    return dt.weekday() in WORKING_DAYS


def get_working_hours_in_day(dt: datetime) -> Tuple[datetime, datetime]:
    day_start = dt.replace(
        hour=WORKING_HOURS_START, minute=0, second=0, microsecond=0
    )
    day_end = dt.replace(
        hour=WORKING_HOURS_END, minute=0, second=0, microsecond=0
    )
    return day_start, day_end


def get_lunch_break(dt: datetime) -> Tuple[datetime, datetime]:
    lunch_start = dt.replace(
        hour=LUNCH_BREAK_START, minute=0, second=0, microsecond=0
    )
    lunch_end = dt.replace(
        hour=LUNCH_BREAK_END, minute=0, second=0, microsecond=0
    )
    return lunch_start, lunch_end


def calculate_working_hours(start: datetime, end: datetime) -> float:
    if start >= end:
        return 0.0

    total_seconds = 0.0
    current = start

    while current < end:
        if is_working_day(current):
            day_start, day_end = get_working_hours_in_day(current)
            lunch_start, lunch_end = get_lunch_break(current)

            period_start = max(current, day_start)
            period_end = min(end, day_end)

            if period_start < period_end:
                if period_start < lunch_start and period_end > lunch_start:
                    total_seconds += (lunch_start - period_start).total_seconds()
                    period_start = lunch_end

                if period_start < period_end:
                    total_seconds += (period_end - period_start).total_seconds()

        current = current + timedelta(days=1)
        current = current.replace(hour=0, minute=0, second=0, microsecond=0)

    return round(total_seconds / 3600, 1)


def calculate_working_days(hours: float) -> float:
    return round(hours / 8, 1)


def calculate_calendar_days(hours: float) -> float:
    return round(hours / 24, 1)


def normalize_to_working_day_start(dt: datetime) -> datetime:
    if not is_working_day(dt):
        days_ahead = (7 - dt.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 1
        dt = dt + timedelta(days=days_ahead)

    return dt.replace(
        hour=WORKING_HOURS_START, minute=0, second=0, microsecond=0
    )


def normalize_to_working_day_end(dt: datetime) -> datetime:
    if not is_working_day(dt):
        days_back = (dt.weekday() - 4) % 7
        if days_back == 0:
            days_back = 1
        dt = dt - timedelta(days=days_back)

    return dt.replace(
        hour=WORKING_HOURS_END, minute=0, second=0, microsecond=0
    )