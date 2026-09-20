"""Тесты для utils/stats.py — calc_stats."""
import pandas as pd
import pytest
from utils.stats import calc_stats


class TestCalcStats:
    """Тесты расчёта статистик (mean, median, P85, count)."""

    def test_empty_series(self):
        """Пустая серия."""
        s = pd.Series(dtype=float)
        mean, median, p85, count = calc_stats(s)
        assert mean == 0.0
        assert median == 0.0
        assert p85 == 0.0
        assert count == 0

    def test_none_series(self):
        """None вместо серии."""
        mean, median, p85, count = calc_stats(None)
        assert mean == 0.0
        assert median == 0.0
        assert p85 == 0.0
        assert count == 0

    def test_all_zeros(self):
        """Все нули — должны игнорироваться (фильтр > 0)."""
        s = pd.Series([0.0, 0.0, 0.0])
        mean, median, p85, count = calc_stats(s)
        assert mean == 0.0
        assert median == 0.0
        assert p85 == 0.0
        assert count == 0

    def test_positive_values(self):
        """Обычные положительные значения."""
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        mean, median, p85, count = calc_stats(s)
        assert abs(mean - 3.0) < 0.01
        assert abs(median - 3.0) < 0.01
        # P85 для 5 элементов: индекс 4 * 0.85 = 3.4 -> интерполяция между 4 и 5
        assert 4.0 <= p85 <= 5.0
        assert count == 5

    def test_mixed_zeros_and_positive(self):
        """Нули смешаны с положительными — нули отсекаются."""
        s = pd.Series([0.0, 2.0, 0.0, 4.0, 6.0])
        mean, median, p85, count = calc_stats(s)
        # только 2, 4, 6
        assert abs(mean - 4.0) < 0.01
        assert abs(median - 4.0) < 0.01
        assert count == 3

    def test_negative_values(self):
        """Отрицательные значения — отсекаются (фильтр > 0)."""
        s = pd.Series([-5.0, -1.0, 2.0, 4.0])
        mean, median, p85, count = calc_stats(s)
        # только 2, 4
        assert abs(mean - 3.0) < 0.01
        assert count == 2

    def test_single_value(self):
        """Одно положительное значение."""
        s = pd.Series([5.0])
        mean, median, p85, count = calc_stats(s)
        assert mean == 5.0
        assert median == 5.0
        assert p85 == 5.0
        assert count == 1

    def test_two_values(self):
        """Два значения — медиана = среднее."""
        s = pd.Series([2.0, 8.0])
        mean, median, p85, count = calc_stats(s)
        assert abs(mean - 5.0) < 0.01
        assert abs(median - 5.0) < 0.01
        assert count == 2

    def test_return_types(self):
        """Проверка типов возвращаемых значений."""
        s = pd.Series([1.0, 2.0, 3.0])
        mean, median, p85, count = calc_stats(s)
        assert isinstance(mean, float)
        assert isinstance(median, float)
        assert isinstance(p85, float)
        assert isinstance(count, int)