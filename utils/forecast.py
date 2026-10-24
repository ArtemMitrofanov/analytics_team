"""utils/forecast.py — Робастный прогноз месячных метрик без внешних зависимостей.

Модель: линейный тренд Theil–Sen по последним ``max_history`` полным месяцам.
Для неотрицательных метрик без верхней границы используется ``log1p``-преобразование,
чтобы прогноз не уходил в минус и меньше реагировал на выбросы. Интервал прогноза
строится по эмпирическим остаткам (P10–P90) и расширяется с горизонтом.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

_MIN_BAND = 1e-9


@dataclass(frozen=True)
class ForecastPoint:
    """Одна точка прогноза."""

    month: pd.Timestamp
    value: float
    lower: float
    upper: float


@dataclass(frozen=True)
class ForecastResult:
    """Результат прогноза одной метрики."""

    available: bool
    points: tuple[ForecastPoint, ...]
    slope: float
    slope_pct: float
    trend: str  # up | down | flat
    status: str  # improving | worsening | stable | changing
    quality: str  # high | medium | low | unavailable
    backtest_mape: float | None
    n_points: int
    method: str
    reason: str = ""


def _clamp(value: float, lower: float | None, upper: float | None) -> float:
    if lower is not None:
        value = max(value, float(lower))
    if upper is not None:
        value = min(value, float(upper))
    return float(value)


def _fit_theil_sen(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Робастная оценка наклона и свободного члена (Theil–Sen)."""
    if len(y) < 2:
        return 0.0, float(y[0]) if len(y) else 0.0

    slopes: list[float] = []
    for i in range(len(y) - 1):
        dx = x[i + 1 :] - x[i]
        dy = y[i + 1 :] - y[i]
        valid = np.abs(dx) > _MIN_BAND
        if np.any(valid):
            slopes.extend((dy[valid] / dx[valid]).tolist())

    slope = float(np.median(slopes)) if slopes else 0.0
    intercept = float(np.median(y - slope * x))
    return slope, intercept


def _to_original(values: np.ndarray, use_log: bool) -> np.ndarray:
    return np.expm1(values) if use_log else values


def _to_model(values: np.ndarray, use_log: bool) -> np.ndarray:
    return np.log1p(np.maximum(values, 0.0)) if use_log else values


def _quality(n_points: int, backtest_mape: float | None) -> str:
    if n_points < 4:
        return "unavailable"
    if backtest_mape is None:
        return "low"
    if n_points >= 8 and backtest_mape <= 20.0:
        return "high"
    if n_points >= 6 and backtest_mape <= 40.0:
        return "medium"
    return "low"


def _backtest(
    x: np.ndarray,
    y_model: np.ndarray,
    use_log: bool,
    max_origin: int = 3,
) -> tuple[float | None, float | None]:
    """Rolling-origin backtest. Возвращает (MAPE, MAE) в исходных единицах."""
    n = len(y_model)
    if n < 3:
        return None, None

    errors: list[float] = []
    mape_terms: list[float] = []
    actuals: list[float] = []

    start = max(2, n - max_origin)
    for cut in range(start, n):
        slope, intercept = _fit_theil_sen(x[:cut], y_model[:cut])
        pred_model = intercept + slope * x[cut]
        pred = float(_to_original(np.array([pred_model]), use_log)[0])
        actual = float(_to_original(np.array([y_model[cut]]), use_log)[0])
        errors.append(abs(pred - actual))
        actuals.append(abs(actual))
        if abs(actual) > 1e-9:
            mape_terms.append(abs(pred - actual) / abs(actual))

    if not errors:
        return None, None

    mae = float(np.mean(errors))
    if mape_terms:
        mape = float(np.mean(mape_terms) * 100.0)
    else:
        mean_actual = float(np.mean(actuals)) if actuals else 0.0
        mape = float(mae / mean_actual * 100.0) if mean_actual > 1e-9 else None
    return mape, mae


def forecast_series(
    series: pd.Series,
    horizon: int = 3,
    min_points: int = 4,
    max_history: int = 18,
    direction: str = "down_good",
    lower: float | None = 0.0,
    upper: float | None = None,
    max_horizon: int = 6,
) -> ForecastResult:
    """Построить прогноз по месячному ряду.

    Parameters
    ----------
    series:
        Ряд с DatetimeIndex (первое число месяца) или индексом, приводимым к нему.
        Пропуски (NaN) игнорируются; текущий неполный месяц должен быть исключён
        вызывающим кодом.
    horizon:
        Горизонт в месяцах. Ограничивается ``max_horizon`` (по умолчанию 6).
    min_points:
        Минимум полных месяцев для построения прогноза.
    max_history:
        Сколько последних точек использовать для оценки тренда.
    direction:
        ``up_good`` / ``down_good`` / ``neutral`` — для интерпретации тренда.
    lower, upper:
        Границы метрики. ``lower=0`` и ``upper=None`` включает log1p-преобразование.
    """
    horizon = max(0, min(int(horizon), int(max_horizon)))

    if series is None or len(series) == 0:
        return ForecastResult(
            available=False,
            points=(),
            slope=0.0,
            slope_pct=0.0,
            trend="flat",
            status="stable",
            quality="unavailable",
            backtest_mape=None,
            n_points=0,
            method="Theil–Sen",
            reason="Нет данных для прогноза",
        )

    s = pd.Series(series).copy()
    try:
        s.index = pd.to_datetime(s.index)
        if getattr(s.index, "tz", None) is not None:
            s.index = s.index.tz_localize(None)
    except (TypeError, ValueError):
        return ForecastResult(
            available=False,
            points=(),
            slope=0.0,
            slope_pct=0.0,
            trend="flat",
            status="stable",
            quality="unavailable",
            backtest_mape=None,
            n_points=0,
            method="Theil–Sen",
            reason="Индекс ряда не является датой",
        )

    s = pd.to_numeric(s, errors="coerce").dropna().sort_index()
    if s.empty:
        return ForecastResult(
            available=False,
            points=(),
            slope=0.0,
            slope_pct=0.0,
            trend="flat",
            status="stable",
            quality="unavailable",
            backtest_mape=None,
            n_points=0,
            method="Theil–Sen",
            reason="Нет заполненных значений",
        )

    if len(s) > max_history:
        s = s.iloc[-max_history:]

    # Индекс — первое число месяца; x — число месяцев от первой точки.
    month_index = s.index.to_period("M").to_timestamp()
    first_month = month_index[0]
    x = np.array(
        [(ts.year - first_month.year) * 12 + (ts.month - first_month.month) for ts in month_index],
        dtype=float,
    )
    y_raw = s.to_numpy(dtype=float)
    use_log = lower is not None and float(lower) >= 0.0 and upper is None
    y_model = _to_model(y_raw, use_log)

    n = len(y_model)
    if n < min_points:
        return ForecastResult(
            available=False,
            points=(),
            slope=0.0,
            slope_pct=0.0,
            trend="flat",
            status="stable",
            quality="unavailable",
            backtest_mape=None,
            n_points=n,
            method="Theil–Sen",
            reason=f"Нужно минимум {min_points} полных месяцев",
        )

    slope_model, intercept_model = _fit_theil_sen(x, y_model)
    fitted = intercept_model + slope_model * x
    residuals = y_model - fitted

    residual_center = float(np.median(residuals))
    mad = float(np.median(np.abs(residuals - residual_center)))
    sigma = 1.4826 * mad
    if sigma <= _MIN_BAND and n > 1:
        sigma = float(np.std(residuals, ddof=1))

    if n >= 3:
        q_low, q_high = np.quantile(residuals, [0.10, 0.90])
    else:
        q_low, q_high = -1.2816 * sigma, 1.2816 * sigma

    backtest_mape, _ = _backtest(x, y_model, use_log)
    quality = _quality(n, backtest_mape)

    mean_original = float(np.mean(y_raw)) if len(y_raw) else 0.0
    if use_log:
        slope_pct = float((np.exp(slope_model) - 1.0) * 100.0)
    else:
        slope_pct = (
            float(slope_model / mean_original * 100.0) if mean_original > 1e-9 else 0.0
        )

    if abs(slope_pct) < 2.0:
        trend = "flat"
    elif slope_pct > 0:
        trend = "up"
    else:
        trend = "down"

    if trend == "flat":
        status = "stable"
    elif direction == "up_good":
        status = "improving" if trend == "up" else "worsening"
    elif direction == "down_good":
        status = "improving" if trend == "down" else "worsening"
    else:
        status = "changing"

    last_month = month_index[-1]
    last_x = float(x[-1])
    points: list[ForecastPoint] = []
    for h in range(1, horizon + 1):
        point_model = intercept_model + slope_model * (last_x + h)
        scale = float(np.sqrt(1.0 + h / max(1, n - 1)))
        lower_model = point_model + float(q_low) * scale
        upper_model = point_model + float(q_high) * scale

        point = _clamp(float(_to_original(np.array([point_model]), use_log)[0]), lower, upper)
        low = _clamp(float(_to_original(np.array([lower_model]), use_log)[0]), lower, upper)
        high = _clamp(float(_to_original(np.array([upper_model]), use_log)[0]), lower, upper)
        low, high = min(low, high), max(low, high)

        future_month = (last_month + pd.offsets.MonthBegin(1) + pd.offsets.MonthBegin(h - 1))
        points.append(
            ForecastPoint(
                month=future_month,
                value=point,
                lower=min(low, point),
                upper=max(high, point),
            )
        )

    return ForecastResult(
        available=True,
        points=tuple(points),
        slope=float(slope_model),
        slope_pct=float(slope_pct),
        trend=trend,
        status=status,
        quality=quality,
        backtest_mape=backtest_mape,
        n_points=n,
        method="Theil–Sen",
    )
