"""Тесты помесячного среза метрик."""
import pandas as pd
import pytest

from data.monthly_metrics import (
    build_monthly_metrics,
    format_month,
    get_metric_specs,
    pivot_monthly_metrics,
)


def _summary(rows):
    return pd.DataFrame(rows)


def _base_row(task_id, finished_at, lead=10.0, queue=4.0, work=6.0, flow=60.0,
              qa_cycle=2.0, dev_cycle=8.0, an_cycle=3.0, qa_work=1.0, dev_work=1.0, an_work=1.0):
    return {
        "Задача": task_id,
        "finished_at": finished_at,
        "Полный Lead Time (д.)": lead,
        "Всего очередей (д.)": queue,
        "Чистая работа (д.)": work,
        "Сквозной Flow Efficiency (%)": flow,
        "Циклтайм QA (дни)": qa_cycle,
        "В тестировании (дни)": qa_work,
        "Цикл Разработки (д.)": dev_cycle,
        "В разработке (д.)": dev_work,
        "Цикл Аналитики (д.)": an_cycle,
        "В аналитике (д.)": an_work,
    }


def _metric_value(long_df, month, key):
    row = long_df[(long_df["month"] == pd.Timestamp(month)) & (long_df["metric_key"] == key)]
    return row.iloc[0]["value"] if not row.empty else None


class TestBuildMonthlyMetrics:
    def test_months_and_task_counts(self):
        summary = _summary([
            _base_row("T1", "2026-01-10"),
            _base_row("T2", "2026-01-20"),
            _base_row("T3", "2026-02-05"),
        ])
        result = build_monthly_metrics(summary, today=pd.Timestamp("2026-03-15"))

        months = sorted(result["month"].unique())
        assert list(months) == [
            pd.Timestamp("2026-01-01"),
            pd.Timestamp("2026-02-01"),
        ]
        assert _metric_value(result, "2026-01-01", "tasks_done") == 2
        assert _metric_value(result, "2026-02-01", "tasks_done") == 1

    def test_means_medians_and_p85(self):
        summary = _summary([
            _base_row("T1", "2026-01-10", lead=10.0),
            _base_row("T2", "2026-01-20", lead=20.0),
        ])
        result = build_monthly_metrics(summary, today=pd.Timestamp("2026-03-15"))

        assert _metric_value(result, "2026-01-01", "lead_time_mean") == pytest.approx(15.0)
        assert _metric_value(result, "2026-01-01", "lead_time_median") == pytest.approx(15.0)
        assert _metric_value(result, "2026-01-01", "lead_time_p85") == pytest.approx(18.5)

    def test_partial_current_month(self):
        summary = _summary([
            _base_row("T1", "2026-03-05"),
        ])
        result = build_monthly_metrics(summary, today=pd.Timestamp("2026-03-15"))
        row = result[result["month"] == pd.Timestamp("2026-03-01")].iloc[0]
        assert bool(row["is_partial"]) is True

    def test_month_without_data_is_not_zero_throughput(self):
        summary = _summary([
            _base_row("T1", "2026-01-10"),
            _base_row("T2", "2026-03-10"),
        ])
        data_months = [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-03-01")]
        result = build_monthly_metrics(
            summary,
            data_months=data_months,
            today=pd.Timestamp("2026-04-15"),
        )
        feb = result[result["month"] == pd.Timestamp("2026-02-01")].iloc[0]
        assert bool(feb["has_data"]) is False
        assert pd.isna(feb["value"])

    def test_role_metric_uses_only_tasks_with_role_work(self):
        summary = _summary([
            _base_row("T1", "2026-01-10", qa_cycle=2.0, qa_work=1.0),
            _base_row("T2", "2026-01-20", qa_cycle=10.0, qa_work=0.0),
        ])
        result = build_monthly_metrics(summary, today=pd.Timestamp("2026-03-15"))
        assert _metric_value(result, "2026-01-01", "qa_cycle_mean") == pytest.approx(2.0)
        assert _metric_value(result, "2026-01-01", "qa_cycle_median") == pytest.approx(2.0)

    def test_role_metric_is_empty_when_nobody_had_role_work(self):
        summary = _summary([
            _base_row("T1", "2026-02-10", qa_work=0.0),
        ])
        result = build_monthly_metrics(summary, today=pd.Timestamp("2026-03-15"))
        assert pd.isna(_metric_value(result, "2026-02-01", "qa_cycle_mean"))

    def test_empty_summary(self):
        result = build_monthly_metrics(pd.DataFrame(), today=pd.Timestamp("2026-03-15"))
        assert result.empty

    def test_missing_finished_at_column(self):
        result = build_monthly_metrics(
            pd.DataFrame({"Задача": ["T1"]}),
            today=pd.Timestamp("2026-03-15"),
        )
        assert result.empty

    def test_pivot_contains_n_and_meta(self):
        summary = _summary([_base_row("T1", "2026-01-10")])
        long_df = build_monthly_metrics(summary, today=pd.Timestamp("2026-03-15"))
        wide = pivot_monthly_metrics(long_df)

        assert "lead_time_mean" in wide.columns
        assert "lead_time_mean__n" in wide.columns
        assert "is_partial" in wide.columns
        assert wide.loc[pd.Timestamp("2026-01-01"), "lead_time_mean__n"] == 1

    def test_metric_groups(self):
        assert {spec.group for spec in get_metric_specs()} == {"core", "qa", "dev", "an"}
        assert all(spec.group == "qa" for spec in get_metric_specs("qa"))

    def test_format_month_ru(self):
        assert format_month(pd.Timestamp("2026-03-01")) == "Март 2026"
