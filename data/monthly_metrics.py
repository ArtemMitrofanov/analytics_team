"""data/monthly_metrics.py — Помесячный срез метрик по завершённым задачам.

Модуль не обращается к базе данных: на вход подаётся уже рассчитанный
``global_summary_df`` из ``data.pipeline``. Задача относится к месяцу, в котором
она была завершена (``finished_at``), — так же, как во вкладке «Динамика по
периодам».
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

from config import MONTH_NAMES_RU
from utils.stats import calc_stats

CORE_GROUP = "core"
QA_GROUP = "qa"
DEV_GROUP = "dev"
AN_GROUP = "an"

METRIC_GROUP_LABELS: dict[str, str] = {
    CORE_GROUP: "Сквозные",
    QA_GROUP: "QA",
    DEV_GROUP: "Разработка",
    AN_GROUP: "Аналитика",
}


@dataclass(frozen=True)
class MetricSpec:
    """Описание одной метрики помесячного среза."""

    key: str
    label: str
    group: str
    agg: str  # count | mean | median | p85
    column: str | None = None
    filter_column: str | None = None
    unit: str = "д."
    direction: str = "down_good"  # up_good | down_good | neutral
    lower: float | None = 0.0
    upper: float | None = None
    digits: int = 2


METRIC_SPECS: tuple[MetricSpec, ...] = (
    # Сквозные метрики
    MetricSpec(
        "tasks_done",
        "Завершено задач",
        CORE_GROUP,
        "count",
        unit="шт.",
        direction="up_good",
        lower=0.0,
        digits=0,
    ),
    MetricSpec(
        "lead_time_mean",
        "Lead Time, среднее",
        CORE_GROUP,
        "mean",
        column="Полный Lead Time (д.)",
    ),
    MetricSpec(
        "lead_time_median",
        "Lead Time, медиана",
        CORE_GROUP,
        "median",
        column="Полный Lead Time (д.)",
    ),
    MetricSpec(
        "lead_time_p85",
        "Lead Time, P85",
        CORE_GROUP,
        "p85",
        column="Полный Lead Time (д.)",
    ),
    MetricSpec(
        "queue_mean",
        "Очереди, среднее",
        CORE_GROUP,
        "mean",
        column="Всего очередей (д.)",
    ),
    MetricSpec(
        "queue_median",
        "Очереди, медиана",
        CORE_GROUP,
        "median",
        column="Всего очередей (д.)",
    ),
    MetricSpec(
        "queue_p85",
        "Очереди, P85",
        CORE_GROUP,
        "p85",
        column="Всего очередей (д.)",
    ),
    MetricSpec(
        "work_mean",
        "Чистая работа, среднее",
        CORE_GROUP,
        "mean",
        column="Чистая работа (д.)",
        direction="neutral",
    ),
    MetricSpec(
        "flow_mean",
        "Сквозной Flow, среднее",
        CORE_GROUP,
        "mean",
        column="Сквозной Flow Efficiency (%)",
        unit="%",
        direction="up_good",
        upper=100.0,
        digits=1,
    ),
    # QA
    MetricSpec(
        "qa_cycle_mean",
        "QA: цикл, среднее",
        QA_GROUP,
        "mean",
        column="Циклтайм QA (дни)",
        filter_column="В тестировании (дни)",
    ),
    MetricSpec(
        "qa_cycle_median",
        "QA: цикл, медиана",
        QA_GROUP,
        "median",
        column="Циклтайм QA (дни)",
        filter_column="В тестировании (дни)",
    ),
    MetricSpec(
        "qa_queue_mean",
        "QA: очередь, среднее",
        QA_GROUP,
        "mean",
        column="Очередь ожидания QA (дни)",
        filter_column="В тестировании (дни)",
    ),
    MetricSpec(
        "qa_flow_mean",
        "QA: Flow, среднее",
        QA_GROUP,
        "mean",
        column="Flow Efficiency QA (%)",
        filter_column="В тестировании (дни)",
        unit="%",
        direction="up_good",
        upper=100.0,
        digits=1,
    ),
    # Разработка
    MetricSpec(
        "dev_cycle_mean",
        "Dev: цикл, среднее",
        DEV_GROUP,
        "mean",
        column="Цикл Разработки (д.)",
        filter_column="В разработке (д.)",
    ),
    MetricSpec(
        "dev_cycle_median",
        "Dev: цикл, медиана",
        DEV_GROUP,
        "median",
        column="Цикл Разработки (д.)",
        filter_column="В разработке (д.)",
    ),
    MetricSpec(
        "dev_queue_mean",
        "Dev: очередь, среднее",
        DEV_GROUP,
        "mean",
        column="Очередь/Код Ревью Dev (д.)",
        filter_column="В разработке (д.)",
    ),
    MetricSpec(
        "dev_flow_mean",
        "Dev: Flow, среднее",
        DEV_GROUP,
        "mean",
        column="Flow Разработки (%)",
        filter_column="В разработке (д.)",
        unit="%",
        direction="up_good",
        upper=100.0,
        digits=1,
    ),
    # Аналитика
    MetricSpec(
        "an_cycle_mean",
        "An: цикл, среднее",
        AN_GROUP,
        "mean",
        column="Цикл Аналитики (д.)",
        filter_column="В аналитике (д.)",
    ),
    MetricSpec(
        "an_cycle_median",
        "An: цикл, медиана",
        AN_GROUP,
        "median",
        column="Цикл Аналитики (д.)",
        filter_column="В аналитике (д.)",
    ),
    MetricSpec(
        "an_queue_mean",
        "An: очередь, среднее",
        AN_GROUP,
        "mean",
        column="Очередь/Ревью Аналитики (д.)",
        filter_column="В аналитике (д.)",
    ),
    MetricSpec(
        "an_flow_mean",
        "An: Flow, среднее",
        AN_GROUP,
        "mean",
        column="Flow Аналитики (%)",
        filter_column="В аналитике (д.)",
        unit="%",
        direction="up_good",
        upper=100.0,
        digits=1,
    ),
)

_METRICS_BY_KEY = {spec.key: spec for spec in METRIC_SPECS}
_EMPTY_COLUMNS = [
    "month",
    "metric_key",
    "label",
    "group",
    "value",
    "n",
    "unit",
    "direction",
    "lower",
    "upper",
    "digits",
    "is_partial",
    "has_data",
]


def get_metric_spec(key: str) -> MetricSpec:
    """Вернуть описание метрики по её ключу."""
    return _METRICS_BY_KEY[key]


def get_metric_specs(group: str | None = None) -> tuple[MetricSpec, ...]:
    """Вернуть метрики, опционально отфильтрованные по группе."""
    if group is None:
        return METRIC_SPECS
    return tuple(spec for spec in METRIC_SPECS if spec.group == group)


def _empty_long_df() -> pd.DataFrame:
    return pd.DataFrame(columns=_EMPTY_COLUMNS)


def _to_month_start(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts.to_period("M").to_timestamp()


def _normalize_data_months(data_months: Iterable[Any] | None) -> set[pd.Timestamp] | None:
    """Привести набор месяцев покрытия данных к set of month-start Timestamps."""
    if data_months is None:
        return None
    if isinstance(data_months, (pd.Series, pd.Index)):
        values = list(data_months)
    else:
        values = list(data_months)
    if not values:
        return set()

    months: set[pd.Timestamp] = set()
    for value in values:
        if isinstance(value, pd.Period):
            months.add(value.to_timestamp())
            continue
        ts = pd.to_datetime(value, errors="coerce")
        if pd.isna(ts):
            continue
        if getattr(ts, "tzinfo", None) is not None:
            ts = ts.tz_localize(None)
        months.add(ts.to_period("M").to_timestamp())
    return months


def _metric_value(
    sub: pd.DataFrame,
    spec: MetricSpec,
) -> tuple[float, int]:
    """Рассчитать значение одной метрики для подмножества задач месяца."""
    if spec.column is None or spec.column not in sub.columns:
        return np.nan, 0

    series = pd.to_numeric(sub[spec.column], errors="coerce")
    mean_v, median_v, p85_v, count = calc_stats(series)
    if count == 0:
        return np.nan, 0

    if spec.agg == "mean":
        value = mean_v
    elif spec.agg == "median":
        value = median_v
    elif spec.agg == "p85":
        value = p85_v
    else:
        raise ValueError(f"Неизвестная агрегация метрики: {spec.agg}")
    return float(value), int(count)


def build_monthly_metrics(
    summary_df: pd.DataFrame,
    data_months: Iterable[Any] | None = None,
    today: Any | None = None,
) -> pd.DataFrame:
    """Построить длинную таблицу помесячных метрик.

    Parameters
    ----------
    summary_df:
        ``global_summary_df`` с колонкой ``finished_at``.
    data_months:
        Месяцы, в которых вообще есть события. Если переданы, месяцы вне этого
        набора получают ``has_data=False`` и не смешиваются с нулевым потоком.
    today:
        Дата для определения незавершённого (текущего) месяца. По умолчанию
        ``pd.Timestamp.now()``. Удобно фиксировать в тестах.
    """
    if summary_df is None or summary_df.empty or "finished_at" not in summary_df.columns:
        return _empty_long_df()

    df = summary_df.copy()
    df["finished_at"] = pd.to_datetime(df["finished_at"], errors="coerce")
    if getattr(df["finished_at"].dt, "tz", None) is not None:
        df["finished_at"] = df["finished_at"].dt.tz_localize(None)
    df = df[df["finished_at"].notna()]
    if df.empty:
        return _empty_long_df()

    df["_month"] = df["finished_at"].dt.to_period("M").dt.to_timestamp()
    today_ts = pd.Timestamp(today) if today is not None else pd.Timestamp.now()
    current_month = _to_month_start(today_ts)
    data_month_set = _normalize_data_months(data_months)

    all_months = set(df["_month"].unique())
    if data_month_set is not None:
        all_months |= data_month_set
    if current_month in all_months:
        all_months.add(current_month)

    if not all_months:
        return _empty_long_df()

    month_index = pd.date_range(min(all_months), max(all_months), freq="MS")
    rows: list[dict[str, Any]] = []

    for month in month_index:
        month_tasks = df[df["_month"] == month]
        is_partial = bool(month == current_month)
        has_data = True if data_month_set is None else month in data_month_set

        for spec in METRIC_SPECS:
            if spec.agg == "count":
                value = float(len(month_tasks)) if has_data else np.nan
                n = len(month_tasks) if has_data else 0
            else:
                sub = month_tasks
                if spec.filter_column is not None:
                    if spec.filter_column in sub.columns:
                        sub = sub[pd.to_numeric(sub[spec.filter_column], errors="coerce").fillna(0) > 0]
                    else:
                        sub = sub.head(0)
                value, n = _metric_value(sub, spec)
                if not has_data:
                    value, n = np.nan, 0

            rows.append(
                {
                    "month": month,
                    "metric_key": spec.key,
                    "label": spec.label,
                    "group": spec.group,
                    "value": value,
                    "n": n,
                    "unit": spec.unit,
                    "direction": spec.direction,
                    "lower": spec.lower,
                    "upper": spec.upper,
                    "digits": spec.digits,
                    "is_partial": is_partial,
                    "has_data": has_data,
                }
            )

    return pd.DataFrame(rows, columns=_EMPTY_COLUMNS)


def pivot_monthly_metrics(monthly_df: pd.DataFrame) -> pd.DataFrame:
    """Развернуть длинную таблицу в wide-формат: строки — месяцы, колонки — метрики."""
    if monthly_df is None or monthly_df.empty:
        return pd.DataFrame()

    wide = monthly_df.pivot(index="month", columns="metric_key", values="value")
    wide = wide.sort_index()

    counts = monthly_df.pivot(index="month", columns="metric_key", values="n")
    counts.columns = [f"{column}__n" for column in counts.columns]
    counts = counts.reindex(wide.index)

    meta = (
        monthly_df.groupby("month", sort=True)[["is_partial", "has_data"]]
        .first()
        .reindex(wide.index)
    )
    return wide.join(counts).join(meta)


def format_month(month: Any) -> str:
    """Человекочитаемое название месяца: «Март 2026»."""
    ts = pd.Timestamp(month)
    return f"{MONTH_NAMES_RU.get(ts.month, str(ts.month))} {ts.year}"
