"""Тесты робастного прогноза месячных метрик."""
import numpy as np
import pandas as pd
import pytest

from utils.forecast import forecast_series


def _series(values, start="2025-01-01"):
    return pd.Series(
        values,
        index=pd.date_range(start, periods=len(values), freq="MS"),
    )


class TestForecastSeries:
    def test_linear_series(self):
        # upper=100 отключает log1p-преобразование — проверяем чистый линейный тренд.
        result = forecast_series(
            _series([10, 11, 12, 13, 14, 15, 16, 17]),
            horizon=3,
            upper=100.0,
        )

        assert result.available is True
        assert result.n_points == 8
        values = [point.value for point in result.points]
        assert values == pytest.approx([18.0, 19.0, 20.0], abs=0.05)
        assert result.trend == "up"
        assert result.status == "worsening"  # down_good: рост длительности — плохо

    def test_linear_series_with_up_good(self):
        result = forecast_series(
            _series([10, 11, 12, 13, 14, 15]),
            horizon=1,
            direction="up_good",
        )
        assert result.status == "improving"

    def test_flat_series(self):
        result = forecast_series(_series([5, 5, 5, 5, 5, 5]), horizon=3)

        assert result.available is True
        assert result.trend == "flat"
        assert result.status == "stable"
        assert [point.value for point in result.points] == pytest.approx([5, 5, 5], abs=0.01)

    def test_not_enough_points(self):
        result = forecast_series(_series([1, 2, 3]), horizon=3)

        assert result.available is False
        assert result.points == ()
        assert "минимум" in result.reason.lower()

    def test_empty_series(self):
        result = forecast_series(pd.Series(dtype=float), horizon=3)

        assert result.available is False
        assert result.points == ()

    def test_non_negative_forecast_is_clamped(self):
        result = forecast_series(
            _series([10, 8, 6, 4, 2, 1]),
            horizon=3,
            lower=0.0,
            direction="down_good",
        )

        assert result.available is True
        assert all(point.value >= 0 for point in result.points)
        assert all(point.lower >= 0 for point in result.points)

    def test_percentage_forecast_is_clamped_to_100(self):
        result = forecast_series(
            _series([60, 70, 80, 90, 95, 99]),
            horizon=3,
            lower=0.0,
            upper=100.0,
        )

        assert result.available is True
        assert all(0 <= point.value <= 100 for point in result.points)
        assert all(0 <= point.lower <= 100 for point in result.points)
        assert all(0 <= point.upper <= 100 for point in result.points)

    def test_outlier_does_not_break_trend(self):
        result = forecast_series(
            _series([10, 10, 10, 10, 100]),
            horizon=3,
        )

        assert result.available is True
        # Theil–Sen устойчив к одному выбросу: тренд остаётся околонулевым.
        assert abs(result.slope_pct) < 5.0
        assert [point.value for point in result.points] == pytest.approx([10, 10, 10], abs=2.0)

    def test_history_is_limited(self):
        result = forecast_series(
            _series(list(range(1, 31))),
            horizon=1,
            max_history=12,
        )

        assert result.n_points == 12

    def test_forecast_months_follow_last_month(self):
        result = forecast_series(_series([1, 2, 3, 4, 5]), horizon=3)

        assert [point.month for point in result.points] == [
            pd.Timestamp("2025-06-01"),
            pd.Timestamp("2025-07-01"),
            pd.Timestamp("2025-08-01"),
        ]

    def test_horizon_is_capped(self):
        result = forecast_series(_series([1, 2, 3, 4, 5]), horizon=20)

        assert len(result.points) == 6

    def test_zero_horizon_returns_trend_only(self):
        result = forecast_series(_series([1, 2, 3, 4, 5]), horizon=0)

        assert result.available is True
        assert result.points == ()
        assert result.trend == "up"

    def test_quality_and_backtest(self):
        result = forecast_series(_series([10, 12, 14, 16, 18, 20, 22, 24]), horizon=2)

        assert result.quality in {"high", "medium", "low"}
        assert result.backtest_mape is not None
        assert np.isfinite(result.backtest_mape)
