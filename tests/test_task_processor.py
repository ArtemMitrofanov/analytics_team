"""Тесты для data/task_processor.py — парсинг и расчёт фаз."""
import pandas as pd
import pytest
from data.task_processor import (
    clean_val,
    extract_task_type,
    extract_task_priorities,
    extract_task_estimates,
    extract_task_deadlines,
    process_single_task,
)
from config import CORE_QA_TEAM


class TestCleanVal:
    """Тесты очистки значений."""

    def test_nan_returns_empty(self):
        assert clean_val(pd.NA) == ""
        assert clean_val(float("nan")) == ""

    def test_strips_brackets_and_quotes(self):
        assert clean_val("['value']") == "value"
        assert clean_val('"value"') == "value"
        assert clean_val("  value  ") == "value"

    def test_none_returns_empty(self):
        assert clean_val(None) == ""


class TestExtractTaskType:
    """Тесты определения типа задачи."""

    def test_bug_type(self):
        df = pd.DataFrame({
            "changed_value": ["Type", "Type"],
            "added_values": ["Task", "Bug"],  # последнее = Bug
            "timestamp": ["2024-01-01", "2024-01-02"],
        })
        assert extract_task_type(df) == "Дефект (Bug)"

    def test_task_type(self):
        df = pd.DataFrame({
            "changed_value": ["Тип задачи в проекте"],
            "added_values": ["Task"],
            "timestamp": ["2024-01-01"],
        })
        assert extract_task_type(df) == "Фича / Задача (Task)"

    def test_epic_type(self):
        df = pd.DataFrame({
            "changed_value": ["Тип работы"],
            "added_values": ["Epic"],
            "timestamp": ["2024-01-01"],
        })
        assert extract_task_type(df) == "Эпик (Epic)"

    def test_tech_debt_type(self):
        df = pd.DataFrame({
            "changed_value": ["Type"],
            "added_values": ["Техдолг"],
            "timestamp": ["2024-01-01"],
        })
        assert extract_task_type(df) == "Техдолг"

    def test_run_type(self):
        df = pd.DataFrame({
            "changed_value": ["Type"],
            "added_values": ["Run"],
            "timestamp": ["2024-01-01"],
        })
        assert extract_task_type(df) == "Эксплуатация (Run)"

    def test_unknown_type(self):
        df = pd.DataFrame({
            "changed_value": ["Type"],
            "added_values": ["Unknown"],
            "timestamp": ["2024-01-01"],
        })
        assert extract_task_type(df) == "unknown"

    def test_no_type_column(self):
        df = pd.DataFrame({
            "changed_value": ["State"],
            "added_values": ["In Progress"],
            "timestamp": ["2024-01-01"],
        })
        assert extract_task_type(df) == "Не определен"

    def test_last_change_wins(self):
        """Последнее изменение типа побеждает."""
        df = pd.DataFrame({
            "changed_value": ["Type", "Type", "Type"],
            "added_values": ["Bug", "Task", "Epic"],
            "timestamp": ["2024-01-01", "2024-01-02", "2024-01-03"],
        })
        assert extract_task_type(df) == "Эпик (Epic)"


class TestExtractTaskPriorities:
    """Тесты извлечения приоритетов."""

    def test_priority_russian(self):
        df = pd.DataFrame({
            "changed_value": ["Приоритет по задаче"],
            "added_values": ["Критичный"],
            "timestamp": ["2024-01-01"],
        })
        result = extract_task_priorities(df)
        assert result["Приоритет"] == "Критичный"

    def test_priority_english_mapping(self):
        df = pd.DataFrame({
            "changed_value": ["Priority"],
            "added_values": ["Critical"],
            "timestamp": ["2024-01-01"],
        })
        result = extract_task_priorities(df)
        assert result["Приоритет"] == "Критичный"

    def test_priority_major_to_important(self):
        df = pd.DataFrame({
            "changed_value": ["Priority"],
            "added_values": ["Major"],
            "timestamp": ["2024-01-01"],
        })
        result = extract_task_priorities(df)
        assert result["Приоритет"] == "Важный"

    def test_priority_normal_to_ordinary(self):
        df = pd.DataFrame({
            "changed_value": ["Priority"],
            "added_values": ["Normal"],
            "timestamp": ["2024-01-01"],
        })
        result = extract_task_priorities(df)
        assert result["Приоритет"] == "Обычный"

    def test_priority_minor_to_low(self):
        df = pd.DataFrame({
            "changed_value": ["Priority"],
            "added_values": ["Minor"],
            "timestamp": ["2024-01-01"],
        })
        result = extract_task_priorities(df)
        assert result["Приоритет"] == "Низкий"

    def test_queue_priority(self):
        df = pd.DataFrame({
            "changed_value": ["Приоритет в очереди"],
            "added_values": ["5"],
            "timestamp": ["2024-01-01"],
        })
        result = extract_task_priorities(df)
        assert result["Ранг в очереди"] == "5"

    def test_default_values(self):
        """Дефолтные значения при отсутствии данных."""
        df = pd.DataFrame({"changed_value": ["State"], "added_values": ["In Progress"], "timestamp": ["2024-01-01"]})
        result = extract_task_priorities(df)
        assert result["Приоритет"] == "Не указан"
        assert result["Ранг в очереди"] == "Не задан"


class TestExtractTaskEstimates:
    """Тесты извлечения оценок."""

    def test_all_estimates(self):
        df = pd.DataFrame({
            "changed_value": [
                "Оценка аналитика план",
                "Оценка аналитика факт",
                "Оценка разработка план",
                "Оценка разработка факт",
                "Оценка тестирование план",
                "Оценка тестирование факт",
                "Оценка задачи",
            ],
            "added_values": ["8", "10", "16", "20", "4", "5", "M"],
            "timestamp": ["2024-01-01"] * 7,
        })
        result = extract_task_estimates(df)
        assert result["an_plan"] == "8"
        assert result["an_fact"] == "10"
        assert result["dev_plan"] == "16"
        assert result["dev_fact"] == "20"
        assert result["qa_plan"] == "4"
        assert result["qa_fact"] == "5"
        assert result["task_size"] == "M"

    def test_size_storypoints(self):
        df = pd.DataFrame({
            "changed_value": ["Size"],
            "added_values": ["13"],
            "timestamp": ["2024-01-01"],
        })
        result = extract_task_estimates(df)
        assert result["task_size"] == "13"

    def test_missing_estimates(self):
        df = pd.DataFrame({"changed_value": ["State"], "added_values": ["In Progress"], "timestamp": ["2024-01-01"]})
        result = extract_task_estimates(df)
        assert all(v == "" for v in result.values())


class TestExtractTaskDeadlines:
    """Тесты извлечения дедлайнов."""

    def test_valid_deadline_ms(self):
        # 2024-01-20 00:00:00 UTC в ms
        deadline_ms = "1705708800000"
        df = pd.DataFrame({
            "changed_value": ["Дедлайн заказчика", "Дедлайн заказчика"],
            "added_values": [deadline_ms, deadline_ms],
            "timestamp": ["2024-01-15 10:00:00", "2024-01-18 10:00:00"],
        })
        result = extract_task_deadlines(df, pd.Timestamp("2024-01-22 10:00:00"))
        assert result["has_deadline"] is True
        assert result["deadline_shifts"] == 1
        assert result["sla_status"] == "С опозданием (Overdue)"
        assert result["delay_days"] > 0

    def test_on_time_deadline(self):
        deadline_ms = "1705708800000"  # 2024-01-20
        df = pd.DataFrame({
            "changed_value": ["Дедлайн заказчика"],
            "added_values": [deadline_ms],
            "timestamp": ["2024-01-15 10:00:00"],
        })
        result = extract_task_deadlines(df, pd.Timestamp("2024-01-19 10:00:00"))
        assert result["sla_status"] == "В срок (On-Time)"

    def test_no_deadline(self):
        df = pd.DataFrame({"changed_value": ["State"], "added_values": ["In Progress"], "timestamp": ["2024-01-01"]})
        result = extract_task_deadlines(df, None)
        assert result["has_deadline"] is False
        assert result["sla_status"] == "Без дедлайна"

    def test_invalid_deadline_value(self):
        df = pd.DataFrame({
            "changed_value": ["Дедлайн заказчика"],
            "added_values": ["not-a-number"],
            "timestamp": ["2024-01-01"],
        })
        result = extract_task_deadlines(df, None)
        assert result["has_deadline"] is False

    def test_deadline_slippage(self):
        """Сдвиг дедлайна вперёд."""
        df = pd.DataFrame({
            "changed_value": ["Дедлайн заказчика", "Дедлайн заказчика"],
            "added_values": ["1705708800000", "1706313600000"],  # 2024-01-20 -> 2024-01-27
            "timestamp": ["2024-01-15 10:00:00", "2024-01-20 10:00:00"],
        })
        result = extract_task_deadlines(df, pd.Timestamp("2024-01-28 10:00:00"))
        assert result["deadline_shifts"] == 1
        assert result["deadline_slippage_days"] == 7


class TestProcessSingleTask:
    """Интеграционные тесты process_single_task."""

    def _make_status_df(self, transitions):
        """Создаёт DataFrame с переходами статусов.
        transitions: список (from_status, to_status, timestamp, author)
        """
        rows = []
        for i, (from_s, to_s, ts, author) in enumerate(transitions):
            rows.append({
                "timestamp": ts,
                "changed_value": "Текущий статус",
                "removed_values": from_s,
                "added_values": to_s,
                "author_full_name": author,
            })
        return pd.DataFrame(rows)

    def test_simple_flow_analytic_dev_qa(self):
        """Простой поток: Аналитика -> Разработка -> QA -> Done."""
        status_df = self._make_status_df([
            ("Open", "К аналитике", "2024-01-15 09:00:00", "Аналитик А."),
            ("К аналитике", "В аналитике", "2024-01-15 10:00:00", "Аналитик А."),
            ("В аналитике", "К разработке", "2024-01-16 10:00:00", "Аналитик А."),
            ("К разработке", "В разработке", "2024-01-16 11:00:00", "Разработчик Р."),
            ("В разработке", "К тестированию", "2024-01-17 11:00:00", "Разработчик Р."),
            ("К тестированию", "В тестировании", "2024-01-17 12:00:00", "QA К."),
            ("В тестировании", "Протестировано", "2024-01-18 12:00:00", "QA К."),
        ])
        # Добавляем метаданные
        for col in ["issue_id", "iissue_id", "activity_type"]:
            status_df[col] = ""

        task_df = status_df.copy()
        task_df["timestamp"] = pd.to_datetime(task_df["timestamp"])

        result = process_single_task("TASK-1", task_df, 9, 18, 0.78, 7.0)

        task_row, qa_iters, dev_iters, an_iters, dev_revs, an_revs, reworks = result

        assert task_row["Задача"] == "TASK-1"
        assert task_row["В аналитике (д.)"] > 0
        assert task_row["В разработке (д.)"] > 0
        assert task_row["В тестировании (дни)"] > 0
        assert task_row["Полный Lead Time (д.)"] > 0
        assert len(an_iters) == 1
        assert len(dev_iters) == 1
        assert len(qa_iters) == 1
        assert len(reworks) == 0

    def test_rework_detection(self):
        """Детекция возврата на доработку (QA -> Dev -> QA)."""
        status_df = self._make_status_df([
            ("Open", "К разработке", "2024-01-15 09:00:00", "Менеджер"),
            ("К разработке", "В разработке", "2024-01-15 10:00:00", "Разработчик Р."),
            ("В разработке", "К тестированию", "2024-01-16 10:00:00", "Разработчик Р."),
            ("К тестированию", "В тестировании", "2024-01-16 11:00:00", "QA К."),
            ("В тестировании", "К разработке", "2024-01-17 11:00:00", "QA К."),  # возврат
            ("К разработке", "В разработке", "2024-01-17 12:00:00", "Разработчик Р."),  # фикс
            ("В разработке", "К тестированию", "2024-01-17 14:00:00", "Разработчик Р."),
            ("К тестированию", "В тестировании", "2024-01-17 15:00:00", "QA К."),
            ("В тестировании", "Протестировано", "2024-01-18 10:00:00", "QA К."),
        ])
        for col in ["issue_id", "iissue_id", "activity_type"]:
            status_df[col] = ""
        task_df = status_df.copy()
        task_df["timestamp"] = pd.to_datetime(task_df["timestamp"])

        result = process_single_task("TASK-2", task_df, 9, 18, 0.78, 7.0)

        task_row, qa_iters, dev_iters, an_iters, dev_revs, an_revs, reworks = result

        assert len(reworks) == 1
        assert reworks[0]["Задача"] == "TASK-2"
        assert reworks[0]["Кто вернул (QA)"] == "QA К."
        assert reworks[0]["Разработчик (исправил)"] == "Разработчик Р."
        assert reworks[0]["Время фикса (д.)"] > 0

    def test_core_qa_team_role_detection(self):
        """Определение роли QA (основной vs помогающий)."""
        qa_name = CORE_QA_TEAM[0] if CORE_QA_TEAM else "Тестовый QA"
        status_df = self._make_status_df([
            ("Open", "К тестированию", "2024-01-15 09:00:00", "Менеджер"),
            ("К тестированию", "В тестировании", "2024-01-15 10:00:00", qa_name),
            ("В тестировании", "Протестировано", "2024-01-16 10:00:00", qa_name),
        ])
        for col in ["issue_id", "iissue_id", "activity_type"]:
            status_df[col] = ""
        task_df = status_df.copy()
        task_df["timestamp"] = pd.to_datetime(task_df["timestamp"])

        result = process_single_task("TASK-3", task_df, 9, 18, 0.78, 7.0)

        _, qa_iters, *_ = result
        assert len(qa_iters) == 1
        assert qa_iters[0]["Роль"] == "Основной QA"

    def test_non_core_qa_role(self):
        """Не-QA команда -> помогающая роль."""
        status_df = self._make_status_df([
            ("Open", "К тестированию", "2024-01-15 09:00:00", "Менеджер"),
            ("К тестированию", "В тестировании", "2024-01-15 10:00:00", "Разработчик Р."),  # не QA
            ("В тестировании", "Протестировано", "2024-01-16 10:00:00", "Разработчик Р."),
        ])
        for col in ["issue_id", "iissue_id", "activity_type"]:
            status_df[col] = ""
        task_df = status_df.copy()
        task_df["timestamp"] = pd.to_datetime(task_df["timestamp"])

        result = process_single_task("TASK-4", task_df, 9, 18, 0.78, 7.0)

        _, qa_iters, *_ = result
        assert qa_iters[0]["Роль"] == "Помогающая роль"