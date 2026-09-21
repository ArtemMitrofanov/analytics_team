"""Тесты для data/pipeline.py — пакетная обработка."""
import pandas as pd
import pytest
<<<<<<< HEAD
from data.pipeline import process_all_tasks as process_all_tasks_cached
=======
from data.pipeline import process_all_tasks_cached
>>>>>>> c7b0efa56c7e205b1b045fcc5a20a4380bdd34e3


class TestProcessAllTasksCached:
    """Интеграционные тесты пайплайна."""

    def _make_task_df(self, task_id, transitions, metadata=None):
        """Создаёт DataFrame для одной задачи."""
        rows = []
        for from_s, to_s, ts, author in transitions:
            rows.append({
                "task_identifier": task_id,
                "timestamp": ts,
                "changed_value": "Текущий статус",
                "removed_values": from_s,
                "added_values": to_s,
                "author_full_name": author,
                "issue_id": task_id,
                "iissue_id": "",
                "activity_type": "",
            })
        df = pd.DataFrame(rows)
        if metadata:
            for key, val in metadata.items():
                df[key] = val
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df

    def test_two_tasks_independent(self):
        """Две независимые задачи обрабатываются корректно."""
        task1 = self._make_task_df("TASK-1", [
            ("Open", "К аналитике", "2024-01-15 09:00:00", "Аналитик А."),
            ("К аналитике", "В аналитике", "2024-01-15 10:00:00", "Аналитик А."),
            ("В аналитике", "К разработке", "2024-01-16 10:00:00", "Аналитик А."),
            ("К разработке", "В разработке", "2024-01-16 11:00:00", "Разработчик Р."),
            ("В разработке", "К тестированию", "2024-01-17 11:00:00", "Разработчик Р."),
            ("К тестированию", "В тестировании", "2024-01-17 12:00:00", "QA К."),
            ("В тестировании", "Протестировано", "2024-01-18 12:00:00", "QA К."),
        ])

        task2 = self._make_task_df("TASK-2", [
            ("Open", "К разработке", "2024-01-20 09:00:00", "Менеджер"),
            ("К разработке", "В разработке", "2024-01-20 10:00:00", "Разработчик Р."),
            ("В разработке", "К тестированию", "2024-01-21 10:00:00", "Разработчик Р."),
            ("К тестированию", "В тестировании", "2024-01-21 11:00:00", "QA К."),
            ("В тестировании", "Протестировано", "2024-01-22 11:00:00", "QA К."),
        ])

        full_df = pd.concat([task1, task2], ignore_index=True)

        (
            summary_df,
            qa_iters,
            dev_iters,
            an_iters,
            dev_revs,
            an_revs,
            reworks,
        ) = process_all_tasks_cached(full_df, 9, 18, 0.78, 7.0)

        assert len(summary_df) == 2
        assert set(summary_df["Задача"].tolist()) == {"TASK-1", "TASK-2"}

        # Проверяем, что у каждой задачи есть метрики
        for _, row in summary_df.iterrows():
            assert row["Полный Lead Time (д.)"] > 0
            assert row["Сквозной Flow Efficiency (%)"] >= 0

        # Итерации
        assert len(an_iters) == 1  # только TASK-1
        assert len(dev_iters) == 2
        assert len(qa_iters) == 2

    def test_empty_dataframe(self):
        """Пустой DataFrame возвращает пустые результаты."""
        df = pd.DataFrame(columns=[
            "task_identifier", "timestamp", "changed_value",
            "removed_values", "added_values", "author_full_name",
            "issue_id", "iissue_id", "activity_type"
        ])
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        result = process_all_tasks_cached(df, 9, 18, 0.78, 7.0)

        summary_df, qa_iters, dev_iters, an_iters, dev_revs, an_revs, reworks = result

        assert len(summary_df) == 0
        assert len(qa_iters) == 0
        assert len(dev_iters) == 0
        assert len(an_iters) == 0
        assert len(dev_revs) == 0
        assert len(an_revs) == 0
        assert len(reworks) == 0

    def test_single_task_no_status_changes(self):
        """Задача без смены статусов (только метаданные)."""
        df = pd.DataFrame([{
            "task_identifier": "TASK-1",
            "timestamp": "2024-01-15 10:00:00",
            "changed_value": "Type",
            "removed_values": "",
            "added_values": "Bug",
            "author_full_name": "Менеджер",
            "issue_id": "TASK-1",
            "iissue_id": "",
            "activity_type": "",
        }])
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        summary_df, *_ = process_all_tasks_cached(df, 9, 18, 0.78, 7.0)

        assert len(summary_df) == 1
        assert summary_df.iloc[0]["Задача"] == "TASK-1"
        assert summary_df.iloc[0]["Тип задачи"] == "Дефект (Bug)"
        # Временные метрики должны быть нулевыми
        assert summary_df.iloc[0]["Полный Lead Time (д.)"] == 0.0

    def test_cache_key_changes_with_params(self):
        """Результат меняется при изменении параметров рабочего дня."""
        task = self._make_task_df("TASK-1", [
            ("Open", "В разработке", "2024-01-15 09:00:00", "Разработчик Р."),
            ("В разработке", "Протестировано", "2024-01-15 18:00:00", "QA К."),
        ])
        full_df = pd.concat([task], ignore_index=True)

        # 9-18 = 9 часов
        summary1, *_ = process_all_tasks_cached(full_df, 9, 18, 0.78, 7.0)
        # 10-17 = 7 часов
        summary2, *_ = process_all_tasks_cached(full_df, 10, 17, 0.78, 7.0)

        # Lead time должен отличаться
        assert summary1.iloc[0]["Полный Lead Time (д.)"] != summary2.iloc[0]["Полный Lead Time (д.)"]