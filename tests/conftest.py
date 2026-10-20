"""pytest конфигурация — настройка импорта и тестовой PostgreSQL."""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _database_name(dsn: str) -> str:
    return urlparse(dsn).path.lstrip("/")


def _configure_test_database() -> None:
    test_dsn = os.getenv("ANALYTICS_TEST_DATABASE_URL")
    dsn = test_dsn or os.getenv("ANALYTICS_DATABASE_URL")
    if not dsn:
        return
    name = _database_name(dsn)
    if "test" not in name.lower() and os.getenv("ANALYTICS_ALLOW_UNSAFE_TEST_DB") != "1":
        raise RuntimeError(
            "Тесты очищают таблицы. Используйте базу с 'test' в имени, "
            "например ANALYTICS_TEST_DATABASE_URL=.../analytics_test. "
            "Для осознанного запуска на другой базе задайте ANALYTICS_ALLOW_UNSAFE_TEST_DB=1."
        )
    if test_dsn:
        os.environ["ANALYTICS_DATABASE_URL"] = test_dsn


_configure_test_database()


@pytest.fixture(scope="session")
def database_url() -> str:
    """Пропустить тесты, которым нужна БД, если тестовая база не настроена."""
    dsn = os.getenv("ANALYTICS_DATABASE_URL")
    if not dsn:
        pytest.skip("Задайте ANALYTICS_TEST_DATABASE_URL для тестов PostgreSQL")
    return dsn


@pytest.fixture(scope="session", autouse=True)
def _close_db_pool():
    yield
    try:
        from db import close_pool

        close_pool()
    except Exception:
        pass
