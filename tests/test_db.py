"""tests/test_db.py — тесты DuckDB: загрузка, дедупликация по row_hash и file_hash."""
import pytest
import pandas as pd

from db import (
    load_dataframe_to_db,
    make_file_hash,
    is_file_loaded,
    get_all_events,
    get_summary_stats,
    clear_database,
    make_row_hash,
)


@pytest.fixture(autouse=True)
def _clean_db():
    """Очистка БД перед каждым тестом."""
    clear_database()
    yield
    clear_database()


class TestMakeRowHash:
    """Тесты генерации row_hash."""

    def test_same_row_same_hash(self):
        """Одинаковые строки дают одинаковый хэш."""
        row1 = pd.Series({
            "task_identifier": "TASK-1",
            "timestamp": "2024-01-15 10:00",
            "changed_value": "State",
            "added_values": "In Progress",
            "removed_values": "Open",
            "author_full_name": "User1",
        })
        row2 = pd.Series({
            "task_identifier": "TASK-1",
            "timestamp": "2024-01-15 10:00",
            "changed_value": "State",
            "added_values": "In Progress",
            "removed_values": "Open",
            "author_full_name": "User1",
        })
        assert make_row_hash(row1) == make_row_hash(row2)

    def test_different_timestamp_different_hash(self):
        """Разное время — разный хэш."""
        row1 = pd.Series({
            "task_identifier": "TASK-1", "timestamp": "2024-01-15 10:00",
            "changed_value": "State", "added_values": "In Progress",
            "removed_values": "Open", "author_full_name": "User1",
        })
        row2 = pd.Series({
            "task_identifier": "TASK-1", "timestamp": "2024-01-15 11:00",
            "changed_value": "State", "added_values": "In Progress",
            "removed_values": "Open", "author_full_name": "User1",
        })
        assert make_row_hash(row1) != make_row_hash(row2)

    def test_different_author_different_hash(self):
        """Разный автор — разный хэш."""
        row1 = pd.Series({
            "task_identifier": "TASK-1", "timestamp": "2024-01-15 10:00",
            "changed_value": "State", "added_values": "In Progress",
            "removed_values": "Open", "author_full_name": "User1",
        })
        row2 = pd.Series({
            "task_identifier": "TASK-1", "timestamp": "2024-01-15 10:00",
            "changed_value": "State", "added_values": "In Progress",
            "removed_values": "Open", "author_full_name": "User2",
        })
        assert make_row_hash(row1) != make_row_hash(row2)


class TestMakeFileHash:
    """Тесты генерации file_hash."""

    def test_same_content_same_hash(self):
        content = b"test,csv,data"
        assert make_file_hash(content) == make_file_hash(content)

    def test_different_content_different_hash(self):
        assert make_file_hash(b"data1") != make_file_hash(b"data2")


class TestLoadDataframeToDB:
    """Тесты загрузки DataFrame в DuckDB с дедупликацией."""

    def _make_df(self, task_ids=None):
        if task_ids is None:
            task_ids = ["TASK-1", "TASK-1", "TASK-2"]
        n = len(task_ids)
        base_times = [
            "2024-01-15 10:00", "2024-01-15 11:00", "2024-01-16 10:00",
            "2024-01-16 11:00", "2024-01-17 10:00"
        ]
        return pd.DataFrame({
            "task_identifier": task_ids,
            "timestamp": base_times[:n],
            "changed_value": ["State"] * n,
            "added_values": ["In Progress", "Done", "In Progress", "Done", "In Progress"][:n],
            "removed_values": ["Open", "In Progress", "Open", "In Progress", "Open"][:n],
            "author_full_name": ["User1", "User1", "User2", "User2", "User1"][:n],
        })

    def test_first_load_inserts_rows(self):
        """Первая загрузка — все строки вставляются."""
        df = self._make_df()
        file_hash = "abc123"
        inserted = load_dataframe_to_db(df, "test.csv", file_hash)
        assert inserted == 3

        stats = get_summary_stats()
        assert stats["total_rows"] == 3
        assert stats["unique_tasks"] == 2
        assert stats["loaded_files"] == 1

    def test_duplicate_load_same_file_hash_returns_zero(self):
        """Повторная загрузка того же файла (тот же file_hash) — 0 новых строк."""
        df = self._make_df()
        file_hash = "abc123"
        
        load_dataframe_to_db(df, "test.csv", file_hash)
        inserted = load_dataframe_to_db(df, "test.csv", file_hash)
        
        assert inserted == 0
        stats = get_summary_stats()
        assert stats["total_rows"] == 3  # не изменилось

    def test_duplicate_load_same_row_hash_different_file_hash_returns_zero(self):
        """Те же строки (row_hash), но другой file_hash — 0 новых строк (row_hash дедуп).
        loaded_files остаётся 1, так как строки с hash2 не вставились (row_hash конфликт)."""
        df = self._make_df()
        
        load_dataframe_to_db(df, "test.csv", "hash1")
        inserted = load_dataframe_to_db(df, "test.csv", "hash2")  # другой file_hash
        
        assert inserted == 0
        stats = get_summary_stats()
        assert stats["total_rows"] == 3
        assert stats["loaded_files"] == 1  # hash2 не попал в таблицу (row_hash конфликт)

    def test_new_rows_with_different_row_hash_are_inserted(self):
        """Новые строки (другой row_hash) вставляются даже при том же file_hash."""
        df1 = self._make_df(["TASK-1"])
        df2 = self._make_df(["TASK-3", "TASK-4"])
        
        load_dataframe_to_db(df1, "test.csv", "hash1")
        inserted = load_dataframe_to_db(df2, "test.csv", "hash1")  # тот же file_hash
        
        assert inserted == 2
        stats = get_summary_stats()
        assert stats["total_rows"] == 3  # 1 + 2
        assert stats["unique_tasks"] == 3  # TASK-1, TASK-3, TASK-4


class TestIsFileLoaded:
    """Тесты проверки is_file_loaded."""

    def test_false_before_load(self):
        assert is_file_loaded("nonexistent_hash") is False

    def test_true_after_load(self):
        df = pd.DataFrame({
            "task_identifier": ["TASK-1"],
            "timestamp": ["2024-01-15 10:00"],
            "changed_value": ["State"],
            "added_values": ["In Progress"],
            "removed_values": ["Open"],
            "author_full_name": ["User1"],
        })
        load_dataframe_to_db(df, "test.csv", "file_hash_123")
        assert is_file_loaded("file_hash_123") is True
        assert is_file_loaded("other_hash") is False


class TestGetAllEvents:
    """Тесты чтения событий."""

    def test_returns_all_loaded_events(self):
        df = pd.DataFrame({
            "task_identifier": ["TASK-1", "TASK-2"],
            "timestamp": ["2024-01-15 10:00", "2024-01-16 10:00"],
            "changed_value": ["State", "State"],
            "added_values": ["In Progress", "Done"],
            "removed_values": ["Open", "In Progress"],
            "author_full_name": ["User1", "User2"],
        })
        load_dataframe_to_db(df, "test.csv", "hash1")
        
        events = get_all_events()
        assert len(events) == 2
        assert list(events["task_id"]) == ["TASK-1", "TASK-2"]

    def test_empty_db_returns_empty_df(self):
        events = get_all_events()
        assert events.empty


class TestGetSummaryStats:
    """Тесты статистики БД."""

    def test_empty_db_zero_stats(self):
        stats = get_summary_stats()
        assert stats["total_rows"] == 0
        assert stats["unique_tasks"] == 0
        assert stats["loaded_files"] == 0

    def test_counts_after_load(self):
        df = pd.DataFrame({
            "task_identifier": ["TASK-1", "TASK-1", "TASK-2"],
            "timestamp": ["2024-01-15 10:00", "2024-01-15 11:00", "2024-01-16 10:00"],
            "changed_value": ["State", "State", "State"],
            "added_values": ["In Progress", "Done", "In Progress"],
            "removed_values": ["Open", "In Progress", "Open"],
            "author_full_name": ["User1", "User1", "User2"],
        })
        load_dataframe_to_db(df, "test.csv", "hash1")
        
        stats = get_summary_stats()
        assert stats["total_rows"] == 3
        assert stats["unique_tasks"] == 2
        assert stats["loaded_files"] == 1


class TestClearDatabase:
    """Тест очистки БД."""

    def test_clear_removes_all_data(self):
        df = pd.DataFrame({
            "task_identifier": ["TASK-1"],
            "timestamp": ["2024-01-15 10:00"],
            "changed_value": ["State"],
            "added_values": ["In Progress"],
            "removed_values": ["Open"],
            "author_full_name": ["User1"],
        })
        load_dataframe_to_db(df, "test.csv", "hash1")
        
        clear_database()
        
        stats = get_summary_stats()
        assert stats["total_rows"] == 0
        assert stats["unique_tasks"] == 0
        assert stats["loaded_files"] == 0