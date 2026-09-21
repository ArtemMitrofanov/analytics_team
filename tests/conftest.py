"""pytest конфигурация — настройка путей для импорта модулей."""
import sys
from pathlib import Path

# Тесты в корне, модули в корне - добавляем корень проекта в sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))