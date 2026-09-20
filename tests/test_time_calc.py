"""Тесты для utils/time_calc.py — get_work_minutes."""
import pandas as pd
import pytest
from utils.time_calc import get_work_minutes


class TestGetWorkMinutes:
    """Тесты векторизованного расчёта рабочих минут."""

    def test_same_day_within_hours(self):
        """Один рабочий день, внутри рабочих часов."""
        s = pd.Timestamp("2024-01-15 10:00:00")  # Monday
        e = pd.Timestamp("2024-01-15 14:00:00")
        # 4 часа * 60 * 0.78 = 187.2
        assert abs(get_work_minutes(s, e) - 187.2) < 0.01

    def test_same_day_before_work_hours(self):
        """Начало до рабочего дня."""
        s = pd.Timestamp("2024-01-15 08:00:00")
        e = pd.Timestamp("2024-01-15 10:00:00")
        # только 1 час (9-10) * 60 * 0.78 = 46.8
        assert abs(get_work_minutes(s, e) - 46.8) < 0.01

    def test_same_day_after_work_hours(self):
        """Конец после рабочего дня."""
        s = pd.Timestamp("2024-01-15 17:00:00")
        e = pd.Timestamp("2024-01-15 19:00:00")
        # только 1 час (17-18) * 60 * 0.78 = 46.8
        assert abs(get_work_minutes(s, e) - 46.8) < 0.01

    def test_same_day_weekend(self):
        """Суббота/воскресенье — 0 минут."""
        s = pd.Timestamp("2024-01-13 10:00:00")  # Saturday
        e = pd.Timestamp("2024-01-13 14:00:00")
        assert get_work_minutes(s, e) == 0.0

        s = pd.Timestamp("2024-01-14 10:00:00")  # Sunday
        e = pd.Timestamp("2024-01-14 14:00:00")
        assert get_work_minutes(s, e) == 0.0

    def test_monday_to_friday(self):
        """Понедельник-пятница (5 рабочих дней)."""
        s = pd.Timestamp("2024-01-15 10:00:00")  # Monday
        e = pd.Timestamp("2024-01-19 14:00:00")  # Friday
        # Mon: 8h-1h=7h, Tue-Thu: 3*9h=27h, Fri: 5h = 39h * 60 * 0.78
        # но т.к. start=10, end=14:
        # Mon: 8h (10-18), Tue-Thu: 3*9h=27h, Fri: 5h (9-14) = 40h * 60 * 0.78 = 1872
        expected = 40 * 60 * 0.78
        assert abs(get_work_minutes(s, e) - expected) < 0.01

    def test_monday_to_next_monday(self):
        """Понедельник — следующий понедельник (1 неделя)."""
        s = pd.Timestamp("2024-01-15 10:00:00")  # Monday
        e = pd.Timestamp("2024-01-22 10:00:00")  # Next Monday
        # 5 полных рабочих дней + частичный первый/последний
        # Mon(1): 8h, Tue-Fri: 4*9h=36h, Mon(2): 1h (9-10) = 45h * 60 * 0.78 = 2106
        expected = 45 * 60 * 0.78
        assert abs(get_work_minutes(s, e) - expected) < 0.01

    def test_friday_to_monday(self):
        """Пятница — понедельник (через выходные)."""
        s = pd.Timestamp("2024-01-19 10:00:00")  # Friday
        e = pd.Timestamp("2024-01-22 10:00:00")  # Monday
        # Fri: 8h, Mon: 1h = 9h * 60 * 0.78 = 421.2
        expected = 9 * 60 * 0.78
        assert abs(get_work_minutes(s, e) - expected) < 0.01

    def test_saturday_to_monday(self):
        """Суббота — понедельник."""
        s = pd.Timestamp("2024-01-13 10:00:00")  # Saturday
        e = pd.Timestamp("2024-01-15 14:00:00")  # Monday
        # Sat-Sun: 0, Mon: 5h (9-14) = 5h * 60 * 0.78 = 234
        expected = 5 * 60 * 0.78
        assert abs(get_work_minutes(s, e) - expected) < 0.01

    def test_long_range_one_month(self):
        """Длинный интервал ~1 месяц."""
        s = pd.Timestamp("2024-01-15 10:00:00")
        e = pd.Timestamp("2024-02-15 14:00:00")
        # Должно не падать и давать разумное значение
        result = get_work_minutes(s, e)
        assert result > 0
        # ~22 рабочих дня * 9ч * 60 * 0.78 ~ 9266 минимум
        assert result > 9000

    def test_invalid_inputs(self):
        """Некорректные входные данные."""
        assert get_work_minutes(pd.NaT, pd.Timestamp("2024-01-15")) == 0.0
        assert get_work_minutes(pd.Timestamp("2024-01-15"), pd.NaT) == 0.0
        assert get_work_minutes(
            pd.Timestamp("2024-01-15 10:00:00"),
            pd.Timestamp("2024-01-15 09:00:00")
        ) == 0.0  # end < start

    def test_custom_work_hours(self):
        """Кастомные рабочие часы и ratio."""
        s = pd.Timestamp("2024-01-15 10:00:00")
        e = pd.Timestamp("2024-01-15 14:00:00")
        # 10-18 = 8ч, ratio=1.0
        assert abs(get_work_minutes(s, e, start_h=10, end_h=18, ratio=1.0) - 240) < 0.01
        # 9-17 = 8ч, ratio=0.5
        assert abs(get_work_minutes(s, e, start_h=9, end_h=17, ratio=0.5) - 120) < 0.01

    def test_zero_work_day(self):
        """Нулевой рабочий день (start >= end)."""
        s = pd.Timestamp("2024-01-15 10:00:00")
        e = pd.Timestamp("2024-01-15 14:00:00")
        assert get_work_minutes(s, e, start_h=9, end_h=9) == 0.0
        assert get_work_minutes(s, e, start_h=10, end_h=9) == 0.0