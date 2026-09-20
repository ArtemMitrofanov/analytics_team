import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
TEMPLATES_DIR = BASE_DIR / "frontend" / "templates"
STATIC_DIR = BASE_DIR / "frontend" / "static"

DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

WORKING_HOURS_START = 9
WORKING_HOURS_END = 18
LUNCH_BREAK_START = 13
LUNCH_BREAK_END = 14
WORKING_DAYS = [0, 1, 2, 3, 4]

DEFAULT_AGGREGATIONS = ["median", "mean", "p90", "p75"]
TIME_UNITS = ["hours", "working_days", "calendar_days"]

ANALYTICS_STATUSES = {
    "К аналитике",
    "В аналитике",
    "К ревью (аналитика)",
    "Ревью аналитика",
}

DEVELOPMENT_STATUSES = {
    "К разработке",
    "В разработке",
    "К ревью",
    "Код ревью",
}

TESTING_STATUSES = {
    "К тестированию",
    "В тестировании",
    "Протестировано",
}

COMPLETION_STATUSES = {"Завершено", "Сдача приемка", "Done", "Closed"}

STATUS_STAGE_MAP = {}
for s in ANALYTICS_STATUSES:
    STATUS_STAGE_MAP[s] = "analytics"
for s in DEVELOPMENT_STATUSES:
    STATUS_STAGE_MAP[s] = "development"
for s in TESTING_STATUSES:
    STATUS_STAGE_MAP[s] = "testing"

WORK_TYPES = {
    "Разработка",
    "Аналитика",
    "Тестирование",
    "Документирование",
    "Установка",
    "Прочее",
}

FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "true").lower() == "true"

MAX_FILE_SIZE_MB = 50
ALLOWED_EXTENSIONS = {".csv"}

PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.20.0.min.js"
BOOTSTRAP_CDN = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css"