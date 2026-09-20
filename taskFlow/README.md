# TaskFlow Analytics

Сервис аналитики задач для анализа истории задач из системы YouTrack. Предназначен для руководства и лидов команд разработки, аналитики и тестирования.

## Возможности

- **Визуализация прогресса** - наглядные HTML-отчеты о ходе выполнения задач
- **Выявление узких мест** - автоматическое определение этапов разработки, на которых задачи задерживаются дольше всего
- **Оценка эффективности** - анализ временных затрат (Lead Time, Cycle Time) и трудозатрат
- **Интерактивный дашборд** - единая страница с интерактивными графиками для быстрой оценки состояния проекта

## Метрики

- **Lead Time** - от создания задачи до статуса "Завершено"
- **Cycle Time** - от "К разработке" до "Завершено"
- **Stage Time** - время на каждом этапе (Аналитика, Разработка, Тестирование)
- **Распределение задач** - по исполнителям, статусам, приоритетам, типам, спринтам
- **Трудозатраты** - по типам работ, исполнителям, месяцам/кварталам
- **Диаграмма Санкей** - поток задач между статусами

## Установка

### Локальная установка

```bash
# Клонирование репозитория
git clone <repository_url>
cd taskflow-analytics

# Создание виртуального окружения
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# Установка зависимостей
pip install -r requirements.txt
```

### Docker

```bash
# Сборка и запуск
docker-compose up -d

# Для разработки
docker-compose --profile dev up -d
```

## Использование

### Генерация отчета из командной строки

```bash
# Использование файла по умолчанию (data/input.csv)
python src/main.py --mode generate

# Указание входного файла
python src/main.py --mode generate --input data/your_file.csv

# Указание выходного файла
python src/main.py --mode generate --input data/your_file.csv --output output/report.html
```

### Запуск веб-сервера

```bash
# Запуск сервера
python src/main.py --mode server

# Сервер будет доступен по адресу http://localhost:5000
```

### Через Docker

```bash
# Поместите CSV файл в папку data/
cp your_file.csv data/input.csv

# Запуск генерации отчета
docker-compose run --rm taskflow-analytics python src/main.py --mode generate

# Или запуск веб-сервера
docker-compose up -d
```

## Структура проекта

```
taskflow-analytics/
├── data/                 # Входные данные (CSV файлы)
├── output/               # Сгенерированные отчеты
├── src/                  # Исходный код бэкенда
│   ├── config.py         # Конфигурация
│   ├── data_loader.py    # Загрузка и парсинг CSV
│   ├── main.py           # Точка входа
│   ├── app.py            # Flask приложение
│   ├── models/           # Модели данных (Pydantic)
│   ├── processors/       # Бизнес-логика
│   │   ├── timeline_builder.py
│   │   ├── metrics_calculator.py
│   │   ├── worklog_analyzer.py
│   │   └── report_generator.py
│   └── utils/            # Утилиты
│       └── calendar_utils.py
├── frontend/             # Фронтенд
│   ├── templates/        # HTML шаблоны
│   └── static/           # Статические файлы (CSS, JS)
├── tests/                # Тесты
├── requirements.txt      # Зависимости Python
├── Dockerfile            # Docker образ
├── docker-compose.yml    # Docker Compose
└── README.md             # Документация
```

## Формат входного CSV

Ожидается CSV с колонками:
- `issue_id` - идентификатор задачи
- `timestamp` - время события
- `activity_type` - тип активности (CustomFieldActivityItem, WorkItemActivityItem)
- `author` - автор изменения
- `author_full_name` - полное имя автора
- `changed_value` - изменившееся поле
- `added_values` - добавленные значения (JSON/список)
- `removed_values` - удаленные значения (JSON/список)
- `project_id` - ID проекта
- `event_date` - дата события

## Рабочий календарь

- **Рабочие дни:** Понедельник - Пятница
- **Рабочие часы:** 9:00 - 18:00
- **Обеденный перерыв:** 13:00 - 14:00 (1 час)
- **Чистое рабочее время в день:** 8 часов

Время рассчитывается с учетом выходных, нерабочих часов и обеденного перерыва.

## Статусы этапов

### Аналитика
- К аналитике
- В аналитике
- К ревью (аналитика)
- Ревью аналитика

### Разработка
- К разработке
- В разработке
- К ревью
- Код ревью

### Тестирование
- К тестированию
- В тестировании
- Протестировано

### Завершение
- Завершено
- Сдача приемка

## API Endpoints

- `GET /` - главная страница дашборда
- `POST /upload` - загрузка CSV файла и генерация отчета
- `POST /generate` - генерация отчета из существующего файла (JSON: `{"input_file": "filename.csv"}`)
- `GET /download/<filename>` - скачивание отчета
- `GET /health` - проверка здоровья сервиса

## Тестирование

```bash
# Установка зависимостей для тестов
pip install pytest pytest-cov

# Запуск тестов
pytest tests/ -v

# С покрытием
pytest tests/ --cov=src --cov-report=html
```

## Конфигурация

Основные настройки в `src/config.py`:

```python
WORKING_HOURS_START = 9
WORKING_HOURS_END = 18
LUNCH_BREAK_START = 13
LUNCH_BREAK_END = 14
WORKING_DAYS = [0, 1, 2, 3, 4]  # Пн-Пт

MAX_FILE_SIZE_MB = 50
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5000
```

## Лицензия

MIT