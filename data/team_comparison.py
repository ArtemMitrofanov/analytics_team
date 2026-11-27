"""Агрегация командных метрик по дате завершения задачи."""
from datetime import date

import numpy as np
import pandas as pd

from config import TSHIRT_ORDER
from data.workflow import READY_AT, READY_CYCLE, READY_LEAD, READY_STAGE_COLUMNS

COUNT_METRIC = "Завершено задач"
ESTIMATE_METRIC = "Средняя оценка задачи"
DURATION_METRICS = {
    "Lead Time, среднее": READY_LEAD,
    "Разработка, среднее": READY_STAGE_COLUMNS["В разработке"],
    "Аналитика, среднее": READY_STAGE_COLUMNS["В аналитике"],
    "Тестирование, среднее": READY_STAGE_COLUMNS["В тестировании"],
    "Cycle Time, среднее": READY_CYCLE,
}
METRICS = (COUNT_METRIC, *DURATION_METRICS, ESTIMATE_METRIC)
ACTIVE_STAGE_COLUMNS = set(READY_STAGE_COLUMNS.values())
SIZES = {size: index for index, size in enumerate(TSHIRT_ORDER, start=1)}


def completed_in_period(
    summary: pd.DataFrame, start: date, end: date
) -> pd.DataFrame:
    if summary.empty:
        return summary
    dates = pd.to_datetime(summary[READY_AT], errors="coerce")
    in_period = dates.ge(pd.Timestamp(start)) & dates.lt(pd.Timestamp(end) + pd.Timedelta(days=1))
    return summary.loc[in_period].assign(**{READY_AT: dates.loc[in_period]})


def comparison_values(completed: pd.DataFrame) -> dict[str, tuple[float, int]]:
    """Вернуть значение и число задач, вошедших в расчёт каждой метрики."""
    result = {COUNT_METRIC: (len(completed), len(completed))}
    if completed.empty:
        return {**result, **{metric: (np.nan, 0) for metric in METRICS[1:]}}

    for metric, column in DURATION_METRICS.items():
        values = pd.to_numeric(completed[column], errors="coerce")
        if column in ACTIVE_STAGE_COLUMNS:
            values = values[values > 0]
        result[metric] = (values.mean(), int(values.count()))

    estimates = completed["task_size"].astype("string").str.strip()
    values = estimates.str.upper().map(SIZES)
    result[ESTIMATE_METRIC] = (values.mean(), int(values.count()))
    return result
