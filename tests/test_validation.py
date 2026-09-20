"""Тесты для main.py — validate_csv_schema."""
import pandas as pd
import pytest
from main import validate_csv_schema


class TestValidateCSVSchema:
    """Тесты валидации схемы CSV."""

    def test_valid_minimal_csv(self):
        """Минимально валидный CSV."""
        df = pd.DataFrame({
            "timestamp": ["2024-01-15 10:00:00"],
            "changed_value": ["Текущий статус"],
            "added_values": ["В разработке"],
            "removed_values": ["К разработке"],
            "author_full_name": ["Иванов И.И."],
        })
        valid, errors = validate_csv_schema(df, "test.csv")
        assert valid is True
        assert errors == []

    def test_valid_with_optional_columns(self):
        """Валидный CSV с опциональными колонками."""
        df = pd.DataFrame({
            "timestamp": ["2024-01-15 10:00:00"],
            "changed_value": ["Текущий статус"],
            "added_values": ["В разработке"],
            "removed_values": ["К разработке"],
            "author_full_name": ["Иванов И.И."],
            "issue_id": ["TASK-1"],
            "iissue_id": ["12345"],
            "activity_type": ["IssueStateChanged"],
        })
        valid, errors = validate_csv_schema(df, "test.csv")
        assert valid is True
        assert errors == []

    def test_missing_single_column(self):
        """Отсутствует одна обязательная колонка."""
        df = pd.DataFrame({
            "timestamp": ["2024-01-15 10:00:00"],
            "changed_value": ["Текущий статус"],
            "added_values": ["В разработке"],
            # removed_values отсутствует
            "author_full_name": ["Иванов И.И."],
        })
        valid, errors = validate_csv_schema(df, "test.csv")
        assert valid is False
        assert len(errors) == 1
        assert "removed_values" in errors[0]
        assert "test.csv" in errors[0]

    def test_missing_multiple_columns(self):
        """Отсутствуют несколько обязательных колонок."""
        df = pd.DataFrame({
            "timestamp": ["2024-01-15 10:00:00"],
            "changed_value": ["Текущий статус"],
            # added_values, removed_values, author_full_name отсутствуют
        })
        valid, errors = validate_csv_schema(df, "test.csv")
        assert valid is False
        assert len(errors) == 1
        err = errors[0]
        assert "added_values" in err
        assert "removed_values" in err
        assert "author_full_name" in err

    def test_empty_dataframe(self):
        """Пустой DataFrame — все колонки отсутствуют."""
        df = pd.DataFrame()
        valid, errors = validate_csv_schema(df, "test.csv")
        assert valid is False
        assert len(errors) == 1
        err = errors[0]
        for col in ["timestamp", "changed_value", "added_values", "removed_values", "author_full_name"]:
            assert col in err

    def test_case_sensitive_columns(self):
        """Названия колонок чувствительны к регистру."""
        df = pd.DataFrame({
            "Timestamp": ["2024-01-15 10:00:00"],  # большой T
            "changed_value": ["Текущий статус"],
            "added_values": ["В разработке"],
            "removed_values": ["К разработке"],
            "author_full_name": ["Иванов И.И."],
        })
        valid, errors = validate_csv_schema(df, "test.csv")
        assert valid is False
        assert "timestamp" in errors[0]

    def test_extra_columns_allowed(self):
        """Лишние колонки не вызывают ошибку."""
        df = pd.DataFrame({
            "timestamp": ["2024-01-15 10:00:00"],
            "changed_value": ["Текущий статус"],
            "added_values": ["В разработке"],
            "removed_values": ["К разработке"],
            "author_full_name": ["Иванов И.И."],
            "extra_col1": ["data"],
            "extra_col2": ["more data"],
        })
        valid, errors = validate_csv_schema(df, "test.csv")
        assert valid is True
        assert errors == []