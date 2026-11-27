"""config.py — Централизованное хранилище констант, статусов и настроек."""
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent / "config"

def _load_team(key: str, default: list[str]) -> list[str]:
    team_file = CONFIG_DIR / "team.json"
    if team_file.exists():
        with open(team_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get(key, default)
    return default

CORE_QA_TEAM = _load_team("core_qa_team", [
    "Крохалева Татьяна Владимировна",
    "Митрофанов Артём",
    "Стрелок Наталья Владимировна",
    "Островская Татьяна Евгеньевна",
])

CORE_DEV_TEAM = _load_team("core_dev_team", [
    "Берестов Артем Валерьевич",
    "Евсюков Вячеслав Вячеславович",
    "Кондратьева Марьяна Константиновна",
    "Марков Александр Андреевич",
    "Новокшанова Марина Юрьевна",
    "Островский Дмитрий Вадимович",
    "Перевощиков Андрей Сергеевич",
])

CORE_ANALYTICS_TEAM = _load_team("core_analytics_team", [
    "Попова Анна Вячеславовна",
    "Рубинова Елена Николаевна",
    "Цыпаркина Ангелина Владимировна",
    "Швидун Наталья",
])

DEFAULT_TEAM_ID = "default"
CREATION_SIZE_PROJECT = "KBAKontur"
TASK_ESTIMATE_PROJECT = "KBAInternal"
DEFAULT_WORK_START = 9
DEFAULT_WORK_END = 18
DEFAULT_DEDUCT_HOURS = 2.0

TEAM_DISPLAY_LABELS = {
    ("kbainternal", ""): "АБК",
    ("kbakontur", "модернизация. п00277"): "Модернизация",
    ("kbakontur", "мсфо. п00272"): "МСФО",
    ("kba-budg", ""): "Бюджетирование",
    ("finance", ""): "Финансы",
}


@dataclass(frozen=True)
class Team:
    name: str
    qa: tuple[str, ...] = ()
    dev: tuple[str, ...] = ()
    analytics: tuple[str, ...] = ()
    work_start: int = DEFAULT_WORK_START
    work_end: int = DEFAULT_WORK_END
    deduct_hours: float = DEFAULT_DEDUCT_HOURS
    project: str = ""
    subsystem: str = ""
    display_name: str | None = None


def is_msfo_team(team: Team) -> bool:
    return (
        team.project == CREATION_SIZE_PROJECT
        and team.subsystem.strip().rstrip(".").casefold() == "мсфо. п00272"
    )


def uses_first_task_size(team: Team) -> bool:
    return (
        team.project == CREATION_SIZE_PROJECT
        and team.subsystem.strip().rstrip(".").casefold() in {"мсфо. п00272", "модернизация. п00277"}
    )


def team_display_label(team: Team, imported_project: str | None = None) -> str:
    if team.display_name is not None:
        return team.display_name
    project = team.project or imported_project or team.name
    subsystem = team.subsystem.strip().rstrip(".").casefold()
    fallback = team.name if subsystem else imported_project or team.name
    return TEAM_DISPLAY_LABELS.get((project.strip().casefold(), subsystem), fallback)


def _load_teams() -> dict[str, Team]:
    teams = {
        DEFAULT_TEAM_ID: Team(
            "Основная команда", tuple(CORE_QA_TEAM), tuple(CORE_DEV_TEAM),
            tuple(CORE_ANALYTICS_TEAM),
        ),
    }
    configured_path = os.environ.get("ANALYTICS_TEAMS_FILE")
    path = Path(configured_path) if configured_path else CONFIG_DIR / "teams.json"
    if not configured_path and not path.exists():
        return teams
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Файл команд должен содержать объект с идентификаторами команд")
    for team_id, entry in data.items():
        if (
            not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", team_id)
            or not isinstance(entry, dict)
            or not isinstance(entry.get("name"), str)
            or not entry["name"].strip()
        ):
            raise ValueError(f"Некорректная команда в файле настроек: {team_id}")
        previous = teams.get(team_id, Team(entry["name"]))
        roster = {}
        for role in ("qa", "dev", "analytics"):
            if role not in entry:
                roster[role] = getattr(previous, role)
                continue
            members = entry[role]
            if not isinstance(members, list) or not all(
                isinstance(member, str) and member.strip() for member in members
            ):
                raise ValueError(f"Некорректный состав {role} для команды {team_id}")
            roster[role] = tuple(members)
        work_start = entry.get("work_start", DEFAULT_WORK_START)
        work_end = entry.get("work_end", DEFAULT_WORK_END)
        deduct_hours = entry.get("deduct_hours", DEFAULT_DEDUCT_HOURS)
        if (
            type(work_start) is not int or type(work_end) is not int
            or not 0 <= work_start < work_end <= 23
            or type(deduct_hours) not in (int, float)
            or not 0 <= deduct_hours <= min(8, work_end - work_start - 1)
        ):
            raise ValueError(f"Некорректный рабочий график для команды {team_id}")
        project = entry.get("project", "")
        subsystem = entry.get("subsystem", "")
        if (
            not isinstance(project, str) or not isinstance(subsystem, str)
            or bool(project.strip()) != bool(subsystem.strip())
        ):
            raise ValueError(f"Укажите и project, и subsystem для команды {team_id}")
        teams[team_id] = Team(
            entry["name"].strip(), **roster, work_start=work_start,
            work_end=work_end, deduct_hours=float(deduct_hours),
            project=project.strip(), subsystem=subsystem.strip(),
        )
    if len({team.name for team in teams.values()}) != len(teams):
        raise ValueError("Названия команд должны быть уникальными")
    scopes = [(team.project, team.subsystem.casefold()) for team in teams.values() if team.subsystem]
    if len(set(scopes)) != len(scopes):
        raise ValueError("Сочетания project и subsystem должны быть уникальными")
    return teams


TEAMS = _load_teams()


MONTH_NAMES_RU = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
}

TSHIRT_ORDER = ["XS", "S", "M", "L", "XL"]
PRIORITY_ORDER = ["Блокирующий", "Критичный", "Важный", "Обычный", "Низкий", "Не указан"]

# Группы статусов этапов
STATUS_ANALYTICS_WAIT = ["К аналитике"]
STATUS_ANALYTICS_WORK = ["В аналитике"]
STATUS_ANALYTICS_REVIEW = ["К ревью (аналитика)", "Ревью аналитики"]

STATUS_DEV_WAIT = ["К разработке"]
STATUS_DEV_WORK = ["В разработке"]
STATUS_DEV_REVIEW = ["К ревью (разработка)", "Код ревью"]

STATUS_QA_WAIT = ["К тестированию"]
STATUS_QA_WORK = ["В тестировании"]

STATUS_COMPLETION = [
    "Протестировано",
    "К релизу",
    "Релиз (установка доработок на боевой)",
    "Завершено",
]

ALL_TRACKED_STATUSES = (
    STATUS_ANALYTICS_WAIT
    + STATUS_ANALYTICS_WORK
    + STATUS_ANALYTICS_REVIEW
    + STATUS_DEV_WAIT
    + STATUS_DEV_WORK
    + STATUS_DEV_REVIEW
    + STATUS_QA_WAIT
    + STATUS_QA_WORK
)
