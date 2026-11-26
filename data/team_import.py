"""Определение подсистемы файла по журналу изменений задач."""
from ast import literal_eval
from collections.abc import Mapping
from re import escape

import pandas as pd

from config import Team


class WrongTeamImport(ValueError):
    """Файл не соответствует выбранной команде."""


def _parse_subsystems(value: str) -> set[str]:
    value = value.strip()
    if value.startswith("["):
        try:
            values = literal_eval(value)
        except (SyntaxError, ValueError):
            values = [value]
    else:
        values = [value]
    return {item.strip().casefold() for item in values if isinstance(item, str) and item.strip()}


def latest_subsystems(frame: pd.DataFrame) -> set[str]:
    keys = ["issue_id", "changed_value", "timestamp", "added_values"]
    if not set(keys).issubset(frame.columns):
        return set()
    events = frame.loc[
        frame["changed_value"].astype("string").str.strip().str.casefold().eq("subsystem"),
        keys,
    ].dropna(subset=["issue_id"])
    events["timestamp"] = pd.to_datetime(events["timestamp"], format="mixed", errors="coerce", utc=True)
    latest = (
        events.dropna(subset=["timestamp"]).sort_values("timestamp", kind="stable")
        .drop_duplicates("issue_id", keep="last")
    )
    subsystems = set()
    for value in latest["added_values"].dropna():
        subsystems.update(_parse_subsystems(str(value)))
    return subsystems


def check_import_subsystem(
    frame: pd.DataFrame, team_id: str, project: str | None, teams: Mapping[str, Team]
) -> bool:
    """Проверить маршрутизацию и вернуть признак команды с заданной подсистемой."""
    selected = teams.get(team_id)
    uses_subsystem = selected is not None and bool(selected.subsystem)
    if selected is not None and selected.project and project != selected.project:
        raise WrongTeamImport(f"Для команды «{selected.name}» ожидается префикс {selected.project}.")

    project_teams = [
        (key, team) for key, team in teams.items() if team.subsystem and team.project == project
    ]
    if not project_teams:
        return False
    observed = latest_subsystems(frame)
    for key, team in project_teams:
        if observed == {team.subsystem.casefold()} and team_id != key:
            raise WrongTeamImport(f"Файл относится к команде «{team.name}». Строки из файла не загружены.")

    if uses_subsystem:
        if not observed:
            raise WrongTeamImport(f"В файле нет значения Subsystem для команды «{selected.name}».")
        if observed != {selected.subsystem.casefold()}:
            raise WrongTeamImport(f"Для команды «{selected.name}» ожидается Subsystem «{selected.subsystem}».")
        issues = frame["issue_id"].astype("string").str.strip().dropna()
        if not issues[issues.ne("")].str.fullmatch(rf"{escape(project)}-[0-9]+").all():
            raise WrongTeamImport(f"В файле есть задачи с другим префиксом, чем {project}.")
    return uses_subsystem
