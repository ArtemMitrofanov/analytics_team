"""config.py — Централизованное хранилище констант, статусов и настроек."""
import json
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent / "config"

def _load_qa_team() -> list[str]:
    team_file = CONFIG_DIR / "team.json"
    if team_file.exists():
        with open(team_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("core_qa_team", [])
    return [
        "Крохалева Татьяна Владимировна",
        "Митрофанов Артём",
        "Стрелок Наталья Владимировна",
        "Островская Татьяна Евгеньевна",
    ]

CORE_QA_TEAM = _load_qa_team()

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

# Модели LLM для CrewAI
DEFAULT_CREWAI_MODEL = "gemini/gemini-3.6-flash"