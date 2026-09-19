"""pytest конфигурация — настройка путей для импорта модулей."""
import sys
from pathlib import Path

# Тесты теперь внутри app/tests/, добавляем app/ в sys.path
APP_DIR = Path(__file__).resolve().parent.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))