from datetime import date

import pandas as pd
import pytest

from data.pipeline import process_all_tasks
from data.team_comparison import comparison_values, completed_in_period
from data.workflow import READY_AT


def test_comparison_counts_zero_when_no_tasks_reached_release_in_period():
    summary = pd.DataFrame({READY_AT: [None, "2025-12-31"], "Задача": ["A-1", "A-2"]})
    tasks = completed_in_period(summary, date(2026, 1, 1), date(2026, 11, 26))
    assert tasks.empty
    assert comparison_values(tasks)["Завершено задач"] == (0, 0)


def test_comparison_metrics_use_completed_tasks_and_xs_to_xl_estimates():
    events = pd.DataFrame(
        [
            ("T-1", "2024-02-05 09:00", "State", "К аналитике"),
            ("T-1", "2024-02-06 09:00", "State", "В аналитике"),
            ("T-1", "2024-02-07 09:00", "State", "В разработке"),
            ("T-1", "2024-02-08 09:00", "State", "В тестировании"),
            ("T-1", "2024-02-09 09:00", "State", "К релизу"),
            ("T-1", "2024-02-06 10:00", "Оценка задачи", "M"),
            ("T-2", "2024-02-08 09:00", "State", "В разработке"),
            ("T-2", "2024-02-09 18:00", "State", "К релизу"),
            ("T-2", "2024-02-08 10:00", "Size", "8,5"),
            ("T-3", "2024-02-08 09:00", "State", "В разработке"),
            ("T-3", "2024-02-12 09:00", "State", "К релизу"),
            ("T-4", "2024-02-08 09:00", "State", "В разработке"),
        ],
        columns=["task_id", "timestamp", "changed_value", "added_values"],
    ).assign(removed_values="", activity_type="", author_full_name="")
    summary, *_ = process_all_tasks(events, 9, 18, 7 / 9, 7)
    tasks = completed_in_period(summary, date(2024, 2, 9), date(2024, 2, 9))

    values = comparison_values(tasks)
    assert values == {
        "Завершено задач": (2, 2),
        "Lead Time, среднее": (pytest.approx(4), 1),
        "Разработка, среднее": (pytest.approx(1.5), 2),
        "Аналитика, среднее": (pytest.approx(1), 1),
        "Тестирование, среднее": (pytest.approx(1), 1),
        "Cycle Time, среднее": (pytest.approx(2.5), 2),
        "Средняя оценка задачи": (3, 1),
    }


def test_team_comparison_uses_each_projects_overall_estimate_field():
    events = pd.DataFrame(
        [
            ("KBAKontur-1", "2024-02-05 09:00", "Size", "['S']", "IssueCreatedActivityItem"),
            ("KBAKontur-1", "2024-02-06 09:00", "Size", "['XL']", "CustomFieldActivityItem"),
            ("KBAKontur-1", "2024-02-06 10:00", "Оценка разработка план", "L", ""),
            ("KBAKontur-1", "2024-02-07 09:00", "State", "К релизу", ""),
            ("KBAKontur-2", "2024-02-05 09:00", "Size", "[]", "IssueCreatedActivityItem"),
            ("KBAKontur-2", "2024-02-06 09:00", "Size", "['M']", "CustomFieldActivityItem"),
            ("KBAKontur-2", "2024-02-07 09:00", "State", "К релизу", ""),
            ("KBAInternal-1", "2024-02-05 09:00", "Size", "S", "IssueCreatedActivityItem"),
            ("KBAInternal-1", "2024-02-06 09:00", "Size", "XL", "CustomFieldActivityItem"),
            ("KBAInternal-1", "2024-02-07 09:00", "State", "К релизу", ""),
            ("KBAInternal-2", "2024-02-05 09:00", "Оценка задачи", "M", "IssueCreatedActivityItem"),
            ("KBAInternal-2", "2024-02-06 09:00", "Size", "XL", "CustomFieldActivityItem"),
            ("KBAInternal-2", "2024-02-07 09:00", "State", "К релизу", ""),
        ],
        columns=["task_id", "timestamp", "changed_value", "added_values", "activity_type"],
    ).assign(removed_values="", author_full_name="")
    summary, *_ = process_all_tasks(events, 9, 18, 7 / 9, 7)
    assert summary.set_index("Задача")["task_size"].to_dict() == {
        "KBAKontur-1": "S", "KBAKontur-2": "", "KBAInternal-1": "XL", "KBAInternal-2": "M",
    }
    assert summary.loc[summary["Задача"].eq("KBAKontur-1"), "dev_plan"].item() == ""
    tasks = completed_in_period(summary, date(2024, 2, 7), date(2024, 2, 7))
    kontur = tasks[tasks["Задача"].str.startswith("KBAKontur-")]
    internal = tasks[tasks["Задача"].str.startswith("KBAInternal-")]
    assert comparison_values(kontur)["Средняя оценка задачи"] == (2, 1)
    assert comparison_values(internal)["Средняя оценка задачи"] == (4, 2)


def test_finance_stage_history_uses_ready_for_release_and_shows_actual_release_separately():
    events = pd.DataFrame(
        [
            ("Finance-1", "2024-02-01 09:00", "Stage", "Бэклог на квартал"),
            ("Finance-1", "2024-02-05 09:00", "Stage", "К аналитике"),
            ("Finance-1", "2024-02-06 09:00", "Stage", "В работе (аналитика)"),
            ("Finance-1", "2024-02-06 10:00", "State", "Завершено"),
            ("Finance-1", "2024-02-07 09:00", "Stage", "Проектирование в работе"),
            ("Finance-1", "2024-02-08 09:00", "Stage", "В работе (разработка)"),
            ("Finance-1", "2024-02-09 09:00", "Stage", "В работе (код ревью)"),
            ("Finance-1", "2024-02-12 09:00", "Stage", "В работе (тестирование)"),
            ("Finance-1", "2024-02-13 09:00", "Stage", "Ожидание"),
            ("Finance-1", "2024-02-14 09:00", "Stage", "К релизу"),
            ("Finance-1", "2024-02-16 09:00", "Stage", "Зарелизили"),
            ("Finance-2", "2024-02-06 09:00", "Stage", "Проектирование в работе"),
            ("Finance-2", "2024-02-07 09:00", "Stage", "К релизу"),
            ("Finance-3", "2024-02-08 09:00", "Stage", "Зарелизили"),
            ("Other-1", "2024-02-06 09:00", "State", "К аналитике"),
            ("Other-1", "2024-02-07 09:00", "State", "Завершено"),
        ],
        columns=["task_id", "timestamp", "changed_value", "added_values"],
    ).assign(removed_values="", activity_type="", author_full_name="")
    summary, *_ = process_all_tasks(events, 9, 18, 7 / 9, 7)
    finance_task = summary.set_index("Задача").loc["Finance-1"]
    assert finance_task["finished_at"] == pd.Timestamp("2024-02-14 09:00")
    assert finance_task["released_at"] == pd.Timestamp("2024-02-16 09:00")
    assert finance_task["Полный Lead Time (д.)"] == 7
    assert finance_task["Ожидание релиза (д.)"] == 2
    assert finance_task["Проектирование в работе (д.)"] == 1
    assert finance_task["Код ревью (д.)"] == 1
    assert finance_task["Бэклог на квартал (д.)"] == 2
    tasks = completed_in_period(summary, date(2024, 2, 1), date(2024, 2, 29))
    assert tasks["Задача"].tolist() == ["Finance-1", "Finance-2"]
    values = comparison_values(tasks)
    assert values["Lead Time, среднее"] == (7, 1)
    assert values["Cycle Time, среднее"] == (3.5, 2)
    assert values["Аналитика, среднее"] == (1, 1)
    assert values["Разработка, среднее"] == (1, 1)
    assert values["Тестирование, среднее"] == (1, 1)


def test_budget_ready_aliases_count_each_task_once_at_the_first_transition():
    events = pd.DataFrame(
        [
            ("KBABudg-1", "2026-01-05", "К аналитике"),
            ("KBABudg-1", "2026-01-06", "Протестировано (к релизу)"),
            ("KBABudg-1", "2026-02-05", "Готово к переносу (релиз)"),
            ("KBA-Budg-2", "2026-01-12", "В аналитике"),
            ("KBA-Budg-2", "2026-01-13", "Готово к переносу (релиз)"),
            ("Other-1", "2026-01-13", "Готово к переносу (релиз)"),
        ],
        columns=["task_id", "timestamp", "added_values"],
    ).assign(changed_value="State", removed_values="", activity_type="", author_full_name="")
    summary, *_ = process_all_tasks(events, 9, 18, 7 / 9, 7)
    january = completed_in_period(summary, date(2026, 1, 1), date(2026, 1, 31))
    assert january["Задача"].tolist() == ["KBABudg-1", "KBA-Budg-2"]
    assert completed_in_period(summary, date(2026, 2, 1), date(2026, 2, 28)).empty
    assert comparison_values(january)["Lead Time, среднее"] == (1, 2)


def test_msfo_and_modernization_use_first_nonempty_size_and_track_changes():
    from config import Team, uses_first_task_size
    from data.task_processor import extract_task_estimates

    msfo = Team("Другое отображаемое имя", project="KBAKontur", subsystem="МСФО. п00272")
    modernization = Team("Модернизация", project="KBAKontur", subsystem="Модернизация. п00277")
    other = Team("Другая команда", project="KBAKontur", subsystem="Другая подсистема")
    history = pd.DataFrame(
        [
            ("2026-03-01", "['M']", "CustomFieldActivityItem"),
            ("2026-01-01", "[]", "IssueCreatedActivityItem"),
            ("2026-01-05", "['S']", "CustomFieldActivityItem"),
            ("2026-01-06", "['s']", "CustomFieldActivityItem"),
            ("2026-02-01", "[]", "CustomFieldActivityItem"),
            ("2026-03-02", "['S']", "CustomFieldActivityItem"),
        ],
        columns=["timestamp", "added_values", "activity_type"],
    ).assign(changed_value="Size")
    for team in (msfo, modernization):
        result = extract_task_estimates(
            history, project=team.project, first_task_size=uses_first_task_size(team),
        )
        assert result["task_size"] == "S"
        assert result["task_size_changes"] == 2
    other_result = extract_task_estimates(
        history, project=other.project, first_task_size=uses_first_task_size(other),
    )
    assert other_result["task_size"] == ""
    assert "task_size_changes" not in other_result


def test_msfo_release_rule_ignores_returns_from_tested_to_development():
    from data.task_processor import process_single_task

    events = pd.DataFrame(
        [
            ("2026-01-12 09:00", "", "К аналитике"),
            ("2026-01-13 09:00", "Протестировано", "В разработке"),
            ("2026-01-14 09:00", "Протестировано", "К разработке"),
            ("2026-01-15 09:00", "В тестировании", "Сдача-Приёмка"),
            ("2026-01-16 09:00", "Сдача-Приёмка", "К релизу"),
        ],
        columns=["timestamp", "removed_values", "added_values"],
    ).assign(changed_value="State", activity_type="", author_full_name="")

    def evaluate(history, msfo_release):
        task, *_ = process_single_task(
            "KBAKontur-1", history, 9, 18, 7 / 9, 7, msfo_release=msfo_release,
        )
        return task[READY_AT]

    assert evaluate(events.iloc[:3], True) is None
    assert evaluate(events, True) == pd.Timestamp("2026-01-15 09:00")
    assert evaluate(events, False) == pd.Timestamp("2026-01-16 09:00")
    for source, target in (
        ("Протестировано", "Сдача-Приёмка"),
        ("В тестировании", "Завершено"),
    ):
        direct = events.iloc[[0, 3]].copy()
        direct.loc[3, ["removed_values", "added_values"]] = [source, target]
        assert evaluate(direct, True) == pd.Timestamp("2026-01-15 09:00")
