"""utils/time_calc.py — Оптимизированный расчет эффективных рабочих минут."""
import pandas as pd
import numpy as np

def get_work_minutes(
    s_dt: pd.Timestamp,
    e_dt: pd.Timestamp,
    start_h: int = 9,
    end_h: int = 18,
    ratio: float = 0.78
) -> float:
    """Вычисляет количество рабочих минут между двумя датами с учетом рабочих часов и вычета созвонов/обеда."""
    if pd.isna(s_dt) or pd.isna(e_dt) or s_dt >= e_dt:
        return 0.0

    # Быстрый расчет для событий внутри одного и того же дня
    if s_dt.date() == e_dt.date():
        if s_dt.weekday() >= 5:
            return 0.0
        d_start = s_dt.replace(hour=start_h, minute=0, second=0, microsecond=0)
        d_end = s_dt.replace(hour=end_h, minute=0, second=0, microsecond=0)
        overlap_start = max(s_dt, d_start)
        overlap_end = min(e_dt, d_end)
        if overlap_end > overlap_start:
            return ((overlap_end - overlap_start).total_seconds() / 60.0) * ratio
        return 0.0

    # Если события охватывают несколько дней
    mins = 0.0
    cur = s_dt
    while cur.date() <= e_dt.date():
        if cur.weekday() < 5:
            d_start = cur.replace(hour=start_h, minute=0, second=0, microsecond=0)
            d_end = cur.replace(hour=end_h, minute=0, second=0, microsecond=0)
            overlap_start = max(cur, d_start)
            overlap_end = min(e_dt, d_end)
            if overlap_end > overlap_start:
                mins += ((overlap_end - overlap_start).total_seconds() / 60.0) * ratio
        cur = (cur + pd.Timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return mins