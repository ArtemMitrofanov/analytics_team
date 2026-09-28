"""access_control.py — Управление пользователями и правами доступа."""
from typing import Literal
import pandas as pd
import hashlib

Role = Literal["admin", "guest", "analyst", "developer", "tester"]

def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

ALL_TABS = [
    "overview",      # 🌐 Общая информация
    "periods",       # 📅 Динамика по периодам
    "estimates",     # 🎯 Оценка задач
    "deadlines",     # ⏰ Контроль дедлайнов (SLA)
    "types",         # 🐞 Дефекты vs Фичи
    "priorities",    # ⚡ Приоритеты и Очереди
    "qa",            # 🧪 Аудит тестирования QA
    "dev",           # 💻 Аудит разработки
    "analytics",     # 📐 Аудит аналитики
    "detail",        # 🔍 Детализация по задаче
]

ROLE_TABS: dict[Role, list[str]] = {
    "admin": ALL_TABS,
    "guest": ["overview", "periods", "detail"],
    "analyst": ["overview", "periods", "estimates", "types", "priorities", "analytics", "detail"],
    "developer": ["overview", "periods", "estimates", "deadlines", "types", "priorities", "dev", "detail"],
    "tester": ["overview", "periods", "types", "priorities", "qa", "detail"],
}

TAB_LABELS = {
    "overview": "🌐 Общая информация",
    "periods": "📅 Динамика по периодам",
    "estimates": "🎯 Оценка задач",
    "deadlines": "⏰ Контроль дедлайнов (SLA)",
    "types": "🐞 Дефекты vs Фичи",
    "priorities": "⚡ Приоритеты и Очереди",
    "qa": "🧪 Аудит тестирования QA",
    "dev": "💻 Аудит разработки",
    "analytics": "📐 Аудит аналитики",
    "detail": "🔍 Детализация по задаче",
}

USERS = {
    "admin": {
        "password_hash": _hash("admin123"),
        "role": "admin",
        "display_name": "Администратор",
    },
    "guest": {
        "password_hash": _hash("guest123"),
        "role": "guest",
        "display_name": "Гость",
    },
    "analyst": {
        "password_hash": _hash("analyst123"),
        "role": "analyst",
        "display_name": "Аналитик",
    },
    "developer": {
        "password_hash": _hash("dev123"),
        "role": "developer",
        "display_name": "Разработчик",
    },
    "tester": {
        "password_hash": _hash("tester123"),
        "role": "tester",
        "display_name": "Тестировщик",
    },
}

USERNAMES = list(USERS.keys())


def get_user_role(username: str) -> Role:
    """Возвращает роль пользователя по имени."""
    return USERS.get(username, {}).get("role", "guest")


def get_available_tabs(role: Role) -> list[str]:
    """Возвращает список доступных вкладок для роли."""
    return ROLE_TABS.get(role, ["overview", "detail"])


def get_tab_labels() -> dict[str, str]:
    """Возвращает отображаемые названия вкладок."""
    return TAB_LABELS


def verify_password(username: str, password: str) -> bool:
    """Проверяет пароль пользователя."""
    user = USERS.get(username)
    if not user:
        return False
    return user["password_hash"] == _hash(password)


def get_all_users() -> list[str]:
    """Возвращает список всех имён пользователей для выбора в форме."""
    return USERNAMES


def get_user_display_name(username: str) -> str:
    """Возвращает отображаемое имя пользователя."""
    return USERS.get(username, {}).get("display_name", username)


def filter_summary_by_role(summary_df: pd.DataFrame, role: Role, user_name: str) -> pd.DataFrame:
    """Фильтрует summary_df по роли пользователя."""
    if role == "admin":
        return summary_df
    if role == "guest":
        return summary_df.head(0)
    if role == "tester":
        return summary_df[summary_df.get("В тестировании (дни)", 0) > 0]
    if role == "developer":
        return summary_df[summary_df.get("В разработке (д.)", 0) > 0]
    if role == "analyst":
        return summary_df[summary_df.get("В аналитике (д.)", 0) > 0]
    return summary_df.head(0)


def filter_iter_df_by_role(iter_df: pd.DataFrame, role: Role, user_name: str) -> pd.DataFrame:
    """Фильтрует итерации по исполнителю для роли."""
    if role == "admin":
        return iter_df

    actor_cols = {
        "tester": "Исполнитель",
        "developer": "Разработчик",
        "analyst": "Аналитик",
    }

    actor_col = actor_cols.get(role)
    if actor_col and actor_col in iter_df.columns:
        return iter_df[iter_df[actor_col] == user_name]

    return iter_df