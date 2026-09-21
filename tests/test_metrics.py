"""Тесты для data/metrics.py — пересчёт метрик этапа за выбранный период."""
import pandas as pd
import pytest
from data.metrics import recompute_role_period_metrics
from ui.tabs.role_view import _filter_by_period


def _make_summary(rows):
    return pd.DataFrame(rows)


def _make_iters(rows):
    return pd.DataFrame(rows)


class TestFilterByPeriod:
    """Тесты фильтрации итераций по периоду."""

    def test_iter_inside_period(self):
        it = _make_iters([
            {"Задача": "T1", "Итерация": "#1", "Начало": "2026-08-05 10:00:00", "Завершение": "2026-08-10 18:00:00", "Раб. дней": 3.0},
        ])
        res = _filter_by_period(it, "Начало", pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-31"))
        assert len(res) == 1

    def test_iter_outside_period(self):
        it = _make_iters([
            {"Задача": "T1", "Итерация": "#1", "Начало": "2026-04-24 11:23:02", "Завершение": "2026-04-24 11:48:05", "Раб. дней": 0.04},
        ])
        res = _filter_by_period(it, "Начало", pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-31"))
        assert len(res) == 0

    def test_iter_spans_period(self):
        it = _make_iters([
            {"Задача": "T1", "Итерация": "#1", "Начало": "2026-07-30 10:00:00", "Завершение": "2026-08-05 18:00:00", "Раб. дней": 3.0},
        ])
        res = _filter_by_period(it, "Начало", pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-31"))
        assert len(res) == 1

    def test_empty_df(self):
        res = _filter_by_period(pd.DataFrame(), "Начало", pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-31"))
        assert res is None or res.empty


class TestRecomputeRolePeriodMetrics:
    """Тесты пересчёта сводных метрик за период."""

    def test_qa_no_iterations_in_period(self):
        """Задача с итерацией вне периода не должна попадать в результат."""
        summary = _make_summary([{
            "Задача": "T1",
            "В тестировании (дни)": 5.0,
            "Очередь ожидания QA (дни)": 1.0,
            "Циклтайм QA (дни)": 6.0,
            "Доработки у dev (дни)": 0.0,
            "Итераций QA": 2,
            "Flow Efficiency QA (%)": 80.0,
        }])
        iters = _make_iters([
            {"Задача": "T1", "Итерация": "#1", "Начало": "2026-04-24 11:23:02", "Завершение": "2026-04-24 11:48:05", "Раб. дней": 0.04},
            {"Задача": "T1", "Итерация": "#2", "Начало": "2026-04-20 10:20:14", "Завершение": "2026-04-23 09:07:53", "Раб. дней": 2.33},
        ])
        res = recompute_role_period_metrics(summary, iters, pd.DataFrame(), "qa",
                                            pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-31"),
                                            9, 18, 0.78, 7.0)
        assert res.empty

    def test_qa_iteration_in_period(self):
        """Задача с итерацией в периоде должна быть в результате."""
        summary = _make_summary([{
            "Задача": "T1",
            "В тестировании (дни)": 10.0,
            "Очередь ожидания QA (дни)": 2.0,
            "Циклтайм QA (дни)": 12.0,
            "Доработки у dev (дни)": 0.0,
            "Итераций QA": 2,
            "Flow Efficiency QA (%)": 80.0,
        }])
        iters = _make_iters([
            {"Задача": "T1", "Итерация": "#1", "Начало": "2026-08-01 10:00:00", "Завершение": "2026-08-05 18:00:00", "Раб. дней": 4.0},
        ])
        res = recompute_role_period_metrics(summary, iters, pd.DataFrame(), "qa",
                                            pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-31"),
                                            9, 18, 0.78, 7.0)
        assert len(res) == 1
        assert res.iloc[0]["Задача"] == "T1"
        assert res.iloc[0]["Итераций QA"] == 1
        # "В тестировании" должен быть пересчитан по итерациям августа
        assert res.iloc[0]["В тестировании (дни)"] > 0

    def test_qa_multiple_iterations_mixed(self):
        """Задача с итерациями в разных периодах — учитываются только в периоде."""
        summary = _make_summary([{
            "Задача": "T1",
            "В тестировании (дни)": 20.0,
            "Очередь ожидания QA (дни)": 0.0,
            "Циклтайм QA (дни)": 20.0,
            "Доработки у dev (дни)": 0.0,
            "Итераций QA": 3,
            "Flow Efficiency QA (%)": 100.0,
        }])
        iters = _make_iters([
            {"Задача": "T1", "Итерация": "#1", "Начало": "2026-08-01 10:00:00", "Завершение": "2026-08-03 18:00:00", "Раб. дней": 2.0},
            {"Задача": "T1", "Итерация": "#2", "Начало": "2026-09-01 10:00:00", "Завершение": "2026-09-05 18:00:00", "Раб. дней": 4.0},
            {"Задача": "T1", "Итерация": "#3", "Начало": "2026-07-01 10:00:00", "Завершение": "2026-07-03 18:00:00", "Раб. дней": 2.0},
        ])
        res = recompute_role_period_metrics(summary, iters, pd.DataFrame(), "qa",
                                            pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-31"),
                                            9, 18, 0.78, 7.0)
        assert len(res) == 1
        assert res.iloc[0]["Итераций QA"] == 1
        # Только итерация #1 (август) учитывается
        aug_work = res.iloc[0]["В тестировании (дни)"]
        assert 0 < aug_work < 20.0

    def test_dev_role(self):
        """Пересчёт метрик для Dev: отдельные колонки wait и rev."""
        summary = _make_summary([{
            "Задача": "T1",
            "К разработке (д.)": 3.0,
            "В разработке (д.)": 10.0,
            "Очередь/Код Ревью Dev (д.)": 5.0,
            "Цикл Разработки (д.)": 15.0,
            "Flow Разработки (%)": 66.7,
        }])
        iters = _make_iters([
            {"Задача": "T1", "Итерация": "#1", "Начало": "2026-08-01 10:00:00", "Завершение": "2026-08-10 18:00:00", "Раб. дней": 7.0},
        ])
        revs = _make_iters([
            {"Задача": "T1", "Этап ревью": "Код ревью", "Начало": "2026-08-10 10:00:00", "Завершение": "2026-08-12 18:00:00", "Длительность (д.)": 2.0},
        ])
        res = recompute_role_period_metrics(summary, iters, revs, "dev",
                                            pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-31"),
                                            9, 18, 0.78, 7.0)
        assert len(res) == 1
        row = res.iloc[0]
        assert row["В разработке (д.)"] > 0
        assert row["К разработке (д.)"] == 3.0
        assert row["Ревью кода (д.)"] > 0
        assert row["Очередь/Код Ревью Dev (д.)"] == pytest.approx(3.0 + row["Ревью кода (д.)"], abs=0.01)
        assert row["Цикл Разработки (д.)"] == pytest.approx(row["В разработке (д.)"] + 3.0 + row["Ревью кода (д.)"], abs=0.01)

    def test_analytics_role(self):
        """Пересчёт метрик для Analytics: отдельные колонки wait и rev."""
        summary = _make_summary([{
            "Задача": "T1",
            "К аналитике (д.)": 1.5,
            "В аналитике (д.)": 5.0,
            "Очередь/Ревью Аналитики (д.)": 3.0,
            "Цикл Аналитики (д.)": 9.5,
            "Flow Аналитики (%)": 52.6,
        }])
        iters = _make_iters([
            {"Задача": "T1", "Итерация": "#1", "Начало": "2026-08-01 10:00:00", "Завершение": "2026-08-05 18:00:00", "Раб. дней": 4.0},
        ])
        revs = _make_iters([
            {"Задача": "T1", "Этап ревью": "Ревью аналитики", "Начало": "2026-08-05 10:00:00", "Завершение": "2026-08-07 18:00:00", "Длительность (д.)": 2.0},
        ])
        res = recompute_role_period_metrics(summary, iters, revs, "an",
                                            pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-31"),
                                            9, 18, 0.78, 7.0)
        assert len(res) == 1
        row = res.iloc[0]
        assert row["В аналитике (д.)"] > 0
        assert row["К аналитике (д.)"] == 1.5
        assert row["Ревью аналитики (д.)"] > 0
        assert row["Очередь/Ревью Аналитики (д.)"] == pytest.approx(1.5 + row["Ревью аналитики (д.)"], abs=0.01)
        assert row["Цикл Аналитики (д.)"] == pytest.approx(row["В аналитике (д.)"] + 1.5 + row["Ревью аналитики (д.)"], abs=0.01)

    def test_unknown_role_raises(self):
        summary = _make_summary([{"Задача": "T1"}])
        with pytest.raises(ValueError, match="Неизвестная роль"):
            recompute_role_period_metrics(summary, pd.DataFrame(), pd.DataFrame(), "unknown",
                                          pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-31"),
                                          9, 18, 0.78, 7.0)

    def test_empty_summary(self):
        res = recompute_role_period_metrics(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), "qa",
                                            pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-31"),
                                            9, 18, 0.78, 7.0)
        assert res.empty

    def test_qa_queue_from_wait_df(self):
        """Очередь QA за период берётся из wait_df (интервалы «К тестированию»)."""
        summary = _make_summary([{
            "Задача": "T1",
            "В тестировании (дни)": 10.0,
            "Очередь ожидания QA (дни)": 5.0,
            "Циклтайм QA (дни)": 15.0,
            "Доработки у dev (дни)": 0.0,
            "Итераций QA": 1,
            "Flow Efficiency QA (%)": 66.7,
        }])
        iters = _make_iters([
            {"Задача": "T1", "Итерация": "#1", "Начало": "2026-08-05 10:00:00", "Завершение": "2026-08-10 18:00:00", "Раб. дней": 4.0},
        ])
        waits = _make_iters([
            {"Задача": "T1", "Начало": "2026-08-01 10:00:00", "Завершение": "2026-08-05 18:00:00", "Раб. дней": 4.0},
        ])
        res = recompute_role_period_metrics(summary, iters, pd.DataFrame(), "qa",
                                            pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-31"),
                                            9, 18, 0.78, 7.0, wait_df=waits)
        assert len(res) == 1
        assert res.iloc[0]["Очередь ожидания QA (дни)"] > 0
        assert res.iloc[0]["Циклтайм QA (дни)"] > 0
        # Flow = work / (work + queue)
        work = res.iloc[0]["В тестировании (дни)"]
        queue = res.iloc[0]["Очередь ожидания QA (дни)"]
        assert abs(res.iloc[0]["Flow Efficiency QA (%)"] - round(work / (work + queue) * 100, 1)) < 0.2

    def test_qa_queue_wait_outside_period(self):
        """Интервал ожидания вне периода не учитывается."""
        summary = _make_summary([{
            "Задача": "T1",
            "В тестировании (дни)": 10.0,
            "Очередь ожидания QA (дни)": 5.0,
            "Циклтайм QA (дни)": 15.0,
            "Доработки у dev (дни)": 0.0,
            "Итераций QA": 1,
            "Flow Efficiency QA (%)": 66.7,
        }])
        iters = _make_iters([
            {"Задача": "T1", "Итерация": "#1", "Начало": "2026-08-05 10:00:00", "Завершение": "2026-08-10 18:00:00", "Раб. дней": 4.0},
        ])
        waits = _make_iters([
            {"Задача": "T1", "Начало": "2026-04-01 10:00:00", "Завершение": "2026-04-05 18:00:00", "Раб. дней": 4.0},
        ])
        res = recompute_role_period_metrics(summary, iters, pd.DataFrame(), "qa",
                                            pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-31"),
                                            9, 18, 0.78, 7.0, wait_df=waits)
        assert len(res) == 1
        assert res.iloc[0]["Очередь ожидания QA (дни)"] == 0.0

    def test_qa_queue_without_wait_df_falls_back_to_zero(self):
        """Без wait_df очередь QA за период = 0 (старое поведение)."""
        summary = _make_summary([{
            "Задача": "T1",
            "В тестировании (дни)": 10.0,
            "Очередь ожидания QA (дни)": 5.0,
            "Циклтайм QA (дни)": 15.0,
            "Доработки у dev (дни)": 0.0,
            "Итераций QA": 1,
            "Flow Efficiency QA (%)": 66.7,
        }])
        iters = _make_iters([
            {"Задача": "T1", "Итерация": "#1", "Начало": "2026-08-05 10:00:00", "Завершение": "2026-08-10 18:00:00", "Раб. дней": 4.0},
        ])
        res = recompute_role_period_metrics(summary, iters, pd.DataFrame(), "qa",
                                            pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-31"),
                                            9, 18, 0.78, 7.0)
        assert len(res) == 1
        assert res.iloc[0]["Очередь ожидания QA (дни)"] == 0.0
