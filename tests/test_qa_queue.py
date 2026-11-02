"""Проверка дневной очереди: интервалы, переносы, нули и полнота данных."""
import pandas as pd
import pytest

from data.qa_queue import (
    build_queue_daily, build_queue_monthly, is_workday, task_texts, matching_task_ids,
)


def events(*rows):
    return pd.DataFrame([
        {"task_id": task, "timestamp": time, "changed_value": "State",
         "added_values": status, "removed_values": ""}
        for task, time, status in rows
    ])


def daily(raw, through="2026-02-04", **kwargs):
    return build_queue_daily(raw, through, now="2026-02-10", **kwargs)


def test_night_reentry_and_midnight_exit_count_once():
    raw = events(
        ("A", "2026-02-02 00:01", "['К тестированию']"),
        ("A", "2026-02-02 01:00", "В тестировании"),
        ("A", "2026-02-02 23:59:59.999", "К тестированию"),
        ("A", "2026-02-03 00:00", "В тестировании"),
        ("B", "2026-02-02 22:00", "К тестированию"),
        ("B", "2026-02-03 01:00", "В тестировании"),
    )
    result = daily(raw)
    assert result.tasks.tolist() == [2, 1, 0]
    monthly = build_queue_monthly(result).iloc[0]
    assert monthly.average == 1
    assert monthly.workdays == 3


def test_open_task_from_previous_month_survives_period_filter():
    raw = events(("A", "2026-01-30 23:00", "К тестированию"))
    result = daily(raw, start_date="2026-02-02", end_date="2026-02-03")
    assert result.tasks.tolist() == [1, 1]
    assert result.date.dt.day.tolist() == [2, 3]


def test_today_future_and_uncovered_days_excluded():
    raw = events(("A", "2026-02-02 09:00", "К тестированию"))
    result = build_queue_daily(raw, "2026-02-28", now="2026-02-04 23:59")
    assert result.date.dt.day.tolist() == [2, 3]
    result = build_queue_daily(raw, "2026-02-02", now="2026-02-10")
    assert result.date.dt.day.tolist() == [2]


def test_resolution_closes_queue_without_status_change_and_reopen_is_supported():
    raw = events(("A", "2026-02-02 09:00", "К тестированию"),
                 ("A", "2026-02-03 00:00", ""),
                 ("A", "2026-02-04 23:00", "К тестированию"))
    raw["activity_type"] = ["", "IssueResolvedActivityItem", ""]
    raw.loc[1, "changed_value"] = "resolved"
    assert daily(raw).tasks.tolist() == [1, 0, 1]


def test_russian_holiday_transfer_and_working_saturday():
    assert is_workday(pd.Timestamp("2025-11-01"))
    assert not is_workday(pd.Timestamp("2025-11-03"))
    assert not is_workday(pd.Timestamp("2026-01-09"))
    assert is_workday(pd.Timestamp("2026-11-03"))  # сокращённый день
    assert sum(is_workday(d) for d in pd.date_range("2026-01-01", "2026-12-31")) == 247


def test_timezone_and_task_without_testing_work():
    raw = events(("A", "2026-02-01T20:00:00+00:00", "К тестированию"),
                 ("A", "2026-02-01T21:00:00+00:00", "К разработке"))
    result = daily(raw, through="2026-02-02")
    assert result.date.iloc[0] == pd.Timestamp("2026-02-02")
    assert result.tasks.tolist() == [1]


def test_empty_and_unknown_calendar():
    assert daily(pd.DataFrame()).empty
    with pytest.raises(ValueError, match="2030"):
        build_queue_daily(events(("A", "2030-02-01", "К тестированию")),
                          "2030-02-02", now="2030-02-10")


def test_title_description_keywords_are_whole_words_case_insensitive_and_literal():
    raw = events(("A", "2026-02-02", "[УУ] Доработка"),
                 ("B", "2026-02-02", "Проверка пд/интеграции"),
                 ("C", "2026-02-02", "Модуль УС."),
                 ("D", "2026-02-02", "СПД и УСЛОВИЯ"),
                 ("E", "2026-02-02", "Связь C++"))
    raw["changed_value"] = ["summary", "description", "Название", "summary", "description"]
    texts = task_texts(raw)
    assert matching_task_ids(texts, ["УУ", "ПД", "УС"]) == {"A", "B", "C"}
    assert matching_task_ids(texts, ["C++"]) == {"E"}
    assert matching_task_ids(texts, ["", " "]) == set()


def test_latest_text_is_used_and_unknown_tasks_are_retained():
    raw = events(("A", "2026-02-02", "УУ старая задача"),
                 ("A", "2026-02-03", "Наша задача"),
                 ("B", "2026-02-02", "К тестированию"),
                 ("C", "2026-02-02", "ПД старое описание"),
                 ("C", "2026-02-03", ""))
    raw["changed_value"] = ["summary", "summary", "State", "description", "description"]
    texts = task_texts(raw)
    assert texts.loc["A", "title"] == "Наша задача"
    assert not texts.loc["B", "has_text"]
    assert not texts.loc["C", "has_text"]
    assert matching_task_ids(texts, ["УУ", "ПД", "УС"]) == set()


def test_exclusion_keeps_zero_days_and_original_coverage():
    raw = events(("A", "2026-02-02", "К тестированию"),
                 ("B", "2026-02-03", "К тестированию"))
    all_tasks = daily(raw)
    filtered = daily(raw, excluded_task_ids={"A"})
    assert filtered.date.equals(all_tasks.date)
    assert filtered.tasks.tolist() == [0, 1, 1]
    assert daily(raw, excluded_task_ids={"A", "B"}).tasks.tolist() == [0, 0, 0]


def test_queue_chart_renders_above_summary_table():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_string('''
import pandas as pd
from ui.tabs.role_view import render_role_tab
summary = pd.DataFrame({"Задача": ["A"], "work": [0.0], "queue": [0.0], "cycle": [0.0], "flow": [0.0]})
raw = pd.DataFrame({"task_id": ["A", "A"], "timestamp": pd.to_datetime(["2026-02-02", "2026-02-05"]),
    "changed_value": ["State", "State"], "added_values": ["К тестированию", "В тестировании"], "removed_values": ["", "К тестированию"]})
render_role_tab("QA", "work", "queue", "cycle", "flow", ["Задача", "work"],
    pd.DataFrame(), pd.DataFrame(), summary, "Исполнитель", 7.0, queue_events=raw)
''').run(timeout=30)
    assert not app.exception
    markdowns = [item.value for item in app.markdown]
    assert markdowns.index("##### Среднее количество задач в очереди «К тестированию»") < markdowns.index(
        "##### Сводная таблица по задачам (в днях)")
    assert len(app.get("plotly_chart")) == 1
    assert app.sidebar.radio[0].value == "Без сторонних задач"
    app.sidebar.text_area[0].set_value("УУ\nПД\nУС")
    app.sidebar.multiselect[0].set_value(["A"])
    app.run()
    assert not app.exception
    assert app.dataframe[-1].value["Задач в очереди"].tolist() == [0, 0, 0]
    app.sidebar.multiselect[1].set_value(["A"])
    app.run()
    assert not app.exception
    assert app.dataframe[-1].value["Задач в очереди"].tolist() == [1, 1, 1]
    app.sidebar.multiselect[1].set_value([])
    app.sidebar.radio[0].set_value("Все задачи")
    app.run()
    assert not app.exception
    assert app.dataframe[-1].value["Задач в очереди"].tolist() == [1, 1, 1]
