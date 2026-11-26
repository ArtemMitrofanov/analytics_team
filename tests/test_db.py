"""tests/test_db.py — тесты PostgreSQL: загрузка, дедупликация по row_hash и file_hash."""
from uuid import uuid4

import pandas as pd
import pytest

import db
from config import Team, team_display_label

from db import (
    WrongTeamImport,
    clear_database,
    create_team,
    delete_team,
    get_all_events,
    get_db_fingerprint,
    get_events_for_tasks,
    get_summary_stats,
    get_team_display_names,
    get_teams,
    is_file_loaded,
    load_dataframe_to_db,
    make_file_hash,
    make_row_hash,
    rename_team,
)


@pytest.fixture(autouse=True)
def _clean_db(database_url):
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
    """Тесты загрузки DataFrame в PostgreSQL с дедупликацией."""

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


class TestPostgresBehaviour:
    """Особенности загрузки через COPY и ON CONFLICT."""

    def test_duplicate_rows_in_single_batch_inserted_once(self):
        """Дубликаты внутри одного файла не создают повторных строк."""
        df = pd.DataFrame({
            "task_identifier": ["TASK-1", "TASK-1"],
            "timestamp": ["2024-01-15 10:00", "2024-01-15 10:00"],
            "changed_value": ["State", "State"],
            "added_values": ["In Progress", "In Progress"],
            "removed_values": ["Open", "Open"],
            "author_full_name": ["User1", "User1"],
        })

        inserted = load_dataframe_to_db(df, "test.csv", "hash1")

        assert inserted == 1
        assert get_summary_stats()["total_rows"] == 1

    def test_null_optional_fields_are_stored(self):
        """Пустые необязательные поля не ломают COPY."""
        df = pd.DataFrame({
            "task_identifier": ["TASK-1"],
            "timestamp": ["2024-01-15 10:00"],
            "changed_value": ["State"],
            "added_values": [None],
            "removed_values": [None],
            "author_full_name": [None],
        })

        assert load_dataframe_to_db(df, "test.csv", "hash1") == 1
        events = get_all_events()
        assert len(events) == 1
        assert pd.isna(events.iloc[0]["added_values"])
        assert pd.isna(events.iloc[0]["author_full_name"])

    def test_empty_strings_stay_empty_strings(self):
        """Пустая строка не превращается в NULL при COPY."""
        df = pd.DataFrame({
            "task_identifier": ["TASK-1"],
            "timestamp": ["2024-01-15 10:00"],
            "changed_value": [""],
            "added_values": [""],
            "removed_values": [""],
            "author_full_name": [""],
        })

        assert load_dataframe_to_db(df, "test.csv", "hash1") == 1
        events = get_all_events()
        assert events.iloc[0]["changed_value"] == ""
        assert events.iloc[0]["added_values"] == ""

    def test_get_events_for_tasks_filters_rows(self):
        """Выборка по списку задач возвращает только нужные строки."""
        df = pd.DataFrame({
            "task_identifier": ["TASK-1", "TASK-2"],
            "timestamp": ["2024-01-15 10:00", "2024-01-16 10:00"],
            "changed_value": ["State", "State"],
            "added_values": ["In Progress", "Done"],
            "removed_values": ["Open", "In Progress"],
            "author_full_name": ["User1", "User2"],
        })
        load_dataframe_to_db(df, "test.csv", "hash1")

        events = get_events_for_tasks(["TASK-2"])

        assert list(events["task_id"]) == ["TASK-2"]

    def test_fingerprint_changes_after_load(self):
        """Отпечаток БД меняется при добавлении строк."""
        empty_fingerprint = get_db_fingerprint()
        df = pd.DataFrame({
            "task_identifier": ["TASK-1"],
            "timestamp": ["2024-01-15 10:00"],
            "changed_value": ["State"],
            "added_values": ["In Progress"],
            "removed_values": ["Open"],
            "author_full_name": ["User1"],
        })
        load_dataframe_to_db(df, "test.csv", "hash1")

        assert get_db_fingerprint() != empty_fingerprint


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
        assert pd.api.types.is_datetime64_any_dtype(events["timestamp"])


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


def test_team_isolation_for_identical_imports():
    team_id = "second-team"
    frame = pd.DataFrame({
        "task_id": ["TASK-1"],
        "timestamp": ["2024-01-15 10:00"],
        "changed_value": ["State"],
    })
    default_fingerprint = get_db_fingerprint()
    try:
        assert load_dataframe_to_db(frame, "tasks.csv", "same-file", team_id=team_id) == 1
        assert load_dataframe_to_db(frame, "tasks.csv", "same-file", team_id=team_id) == 0
        assert is_file_loaded("same-file", team_id=team_id)
        assert not is_file_loaded("same-file")
        assert get_db_fingerprint() == default_fingerprint
        assert get_all_events().empty

        assert load_dataframe_to_db(frame, "tasks.csv", "same-file") == 1
        assert get_summary_stats()["total_rows"] == 1
        assert get_summary_stats(team_id=team_id)["total_rows"] == 1
        assert get_events_for_tasks(["TASK-1"], team_id=team_id)["team_id"].tolist() == [team_id]
        clear_database(team_id=team_id)
        assert get_summary_stats(team_id=team_id)["total_rows"] == 0
        assert get_summary_stats()["total_rows"] == 1
    finally:
        clear_database(team_id=team_id)


def test_import_rejects_wrong_team_before_writing_events():
    primary = "import-validation-primary"
    secondary = "import-validation-secondary"
    unassigned = "import-validation-unassigned"
    primary_rows = pd.DataFrame({
        "issue_id": ["ImportPrimary-1"],
        "timestamp": ["2024-01-15 10:00"],
        "changed_value": ["State"],
    })
    secondary_rows = primary_rows.assign(issue_id="ImportSecondary-2")
    try:
        assert load_dataframe_to_db(
            primary_rows, "primary.csv", "primary-file", team_id=primary, team_name="ImportPrimary",
        ) == 1
        with pytest.raises(WrongTeamImport, match="выбрана «ImportPrimary»"):
            load_dataframe_to_db(
                secondary_rows, "secondary.csv", "secondary-file",
                team_id=primary, team_name="ImportSecondary",
            )
        with pytest.raises(WrongTeamImport, match="уже принадлежит другой команде"):
            load_dataframe_to_db(
                primary_rows, "primary.csv", "primary-file",
                team_id=unassigned, team_name="ImportPrimary",
            )
        assert get_all_events(team_id=primary)["task_id"].tolist() == ["ImportPrimary-1"]
        assert not is_file_loaded("secondary-file", team_id=primary)
        assert get_all_events(team_id=unassigned).empty

        assert load_dataframe_to_db(
            secondary_rows, "secondary.csv", "secondary-file",
            team_id=secondary, team_name="ImportSecondary",
        ) == 1
        assert get_team_display_names([primary, secondary, unassigned]) == {
            primary: "ImportPrimary", secondary: "ImportSecondary",
        }
    finally:
        clear_database(team_id=primary)
        clear_database(team_id=secondary)


def test_admin_can_create_team_with_reserved_import_scope():
    project = f"WebTest-{uuid4().hex}"
    with pytest.raises(PermissionError, match="администратор"):
        create_team("guest", "Forbidden", project)

    team_id = create_team("admin", "Своя команда", project)
    assert get_teams()[team_id].name == "Своя команда"
    with pytest.raises(ValueError, match="уже существует"):
        create_team("admin", "Дубликат", project)

    scoped_id = create_team("admin", "Подсистема", project, "Подпроект")
    frame = pd.DataFrame({
        "issue_id": [f"{project}-1"],
        "timestamp": ["2024-01-15 10:00"],
        "changed_value": ["Subsystem"],
        "added_values": ["['Подпроект']"],
    })
    try:
        with pytest.raises(WrongTeamImport, match="Подсистема"):
            load_dataframe_to_db(frame, "test.csv", "scope-test", team_id=team_id, team_name=project)
        assert load_dataframe_to_db(
            frame, "test.csv", "scope-test", team_id=scoped_id, team_name=project,
        ) == 1
        plain = frame.assign(changed_value="State", added_values="В разработке")
        with pytest.raises(WrongTeamImport, match="ожидается префикс"):
            load_dataframe_to_db(plain, "test.csv", "project-test", team_id=team_id, team_name="Other")
        assert load_dataframe_to_db(
            plain, "test.csv", "project-test", team_id=team_id, team_name=project,
        ) == 1
    finally:
        clear_database(team_id=team_id)
        clear_database(team_id=scoped_id)


@pytest.mark.parametrize("configured", [False, True])
def test_rename_preserves_identity_and_delete_removes_only_team_data(configured, monkeypatch):
    project = f"ManageTest-{uuid4().hex}"
    subsystem = "Подпроект"
    if configured:
        team_id = f"configured-{uuid4().hex}"
        monkeypatch.setitem(db.TEAMS, team_id, Team("Исходная", project=project, subsystem=subsystem))
    else:
        team_id = create_team("admin", "Исходная", project, subsystem)

    source = pd.DataFrame({
        "issue_id": [f"{project}-1"],
        "timestamp": ["2024-01-15 10:00"],
        "changed_value": ["Subsystem"],
        "added_values": ["['Подпроект']"],
    })
    assert load_dataframe_to_db(source, "managed.csv", "managed", team_id=team_id, team_name=project) == 1
    assert load_dataframe_to_db(source, "other.csv", "other") == 1
    with pytest.raises(PermissionError):
        rename_team("guest", team_id, "Нет доступа")
    with pytest.raises(PermissionError):
        delete_team("guest", team_id)

    rename_team("admin", team_id, "Новое имя")
    team = get_teams()[team_id]
    assert (team_display_label(team), team.project, team.subsystem) == ("Новое имя", project, subsystem)
    assert get_summary_stats(team_id=team_id)["total_rows"] == 1

    assert delete_team("admin", team_id) == 1
    db.close_pool()
    assert team_id not in get_teams()
    assert get_summary_stats(team_id=team_id)["total_rows"] == 0
    assert get_summary_stats()["total_rows"] == 1
    with pytest.raises(WrongTeamImport, match="уже удалена"):
        load_dataframe_to_db(source, "managed.csv", "managed", team_id=team_id, team_name=project)
