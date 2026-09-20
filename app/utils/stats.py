"""utils/stats.py — Расчет математических статистик и перцентилей (P85)."""
from typing import Tuple
import pandas as pd

def calc_stats(series: pd.Series) -> Tuple[float, float, float, int]:
    """Возвращает (Mean, Median, P85, Count) для положительных значений."""
    if series is None or series.empty:
        return 0.0, 0.0, 0.0, 0
    act = series[series > 0]
    if not act.empty:
        return (
            float(act.mean()),
            float(act.median()),
            float(act.quantile(0.85)),
            int(len(act)),
        )
    return 0.0, 0.0, 0.0, 0