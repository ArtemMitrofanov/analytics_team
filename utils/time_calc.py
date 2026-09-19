"""utils/time_calc.py — Векторизованный расчет эффективных рабочих минут."""
import pandas as pd
import numpy as np


def get_work_minutes(
    s_dt: pd.Timestamp,
    e_dt: pd.Timestamp,
    start_h: int = 9,
    end_h: int = 18,
    ratio: float = 0.78
) -> float:
    """Вычисляет количество рабочих минут между двумя датами с учетом рабочих часов и вычета созвонов/обеда.
    
    Векторизованная версия: O(1) вместо O(дней) через математический расчет полных недель.
    """
    if pd.isna(s_dt) or pd.isna(e_dt) or s_dt >= e_dt:
        return 0.0

    work_day_minutes = (end_h - start_h) * 60 * ratio
    if work_day_minutes <= 0:
        return 0.0

    s_day = s_dt.normalize()
    e_day = e_dt.normalize()

    if s_day == e_day:
        if s_dt.weekday() >= 5:
            return 0.0
        d_start = s_dt.replace(hour=start_h, minute=0, second=0, microsecond=0)
        d_end = s_dt.replace(hour=end_h, minute=0, second=0, microsecond=0)
        overlap_start = max(s_dt, d_start)
        overlap_end = min(e_dt, d_end)
        if overlap_end > overlap_start:
            return ((overlap_end - overlap_start).total_seconds() / 60.0) * ratio
        return 0.0

    first_day_minutes = 0.0
    if s_dt.weekday() < 5:
        d_start = s_dt.replace(hour=start_h, minute=0, second=0, microsecond=0)
        d_end = s_dt.replace(hour=end_h, minute=0, second=0, microsecond=0)
        overlap_start = max(s_dt, d_start)
        overlap_end = min(e_dt, d_end)
        if overlap_end > overlap_start:
            first_day_minutes = ((overlap_end - overlap_start).total_seconds() / 60.0) * ratio

    last_day_minutes = 0.0
    if e_dt.weekday() < 5:
        d_start = e_dt.replace(hour=start_h, minute=0, second=0, microsecond=0)
        d_end = e_dt.replace(hour=end_h, minute=0, second=0, microsecond=0)
        overlap_start = max(s_dt, d_start)
        overlap_end = min(e_dt, d_end)
        if overlap_end > overlap_start:
            last_day_minutes = ((overlap_end - overlap_start).total_seconds() / 60.0) * ratio

    full_days_start = s_day + pd.Timedelta(days=1)
    full_days_end = e_day - pd.Timedelta(days=1)

    if full_days_start > full_days_end:
        full_work_days = 0
    else:
        total_days = (full_days_end - full_days_start).days + 1
        full_weeks = total_days // 7
        remainder_days = total_days % 7
        remainder_start_weekday = full_days_start.weekday()
        extra_work_days = sum(
            1 for i in range(remainder_days)
            if (remainder_start_weekday + i) % 7 < 5
        )
        full_work_days = full_weeks * 5 + extra_work_days

    return first_day_minutes + last_day_minutes + full_work_days * work_day_minutes