# Team Process Analytics

Комплексный процессный аудит команды: Lead Time, Flow Efficiency, цикл разработки, тестирования и аналитики, SLA и реворки.

## Требования и зависимости

Проверенная конфигурация — **Python 3.12**, Streamlit 1.37.0, Pandas 2.2.2,
NumPy 1.26.4, PyArrow 17.0.0 и PostgreSQL 16 (драйвер psycopg 3). Метаданные
проекта допускают Python 3.10+, но сервер и приведённые ниже команды проверялись
на Python 3.12. Основные зависимости заданы в `pyproject.toml`, все установленные
версии — в `requirements.lock.txt`.

**Не обновляйте PyArrow отдельно:** PyArrow 26.0.0 требует NumPy 2 и вызывает
`ImportError` при отображении таблиц с NumPy 1.26.4. Устанавливайте зависимости
из lock-файла. Перед обновлением PostgreSQL сделайте резервную копию базы.

## Локальный запуск

```bash
git clone https://github.com/ArtemMitrofanov/analytics_team.git
cd analytics_team
test -f .env || cp .env.example .env
docker compose up -d db
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
export ANALYTICS_DATABASE_URL=postgresql://analytics:change-me@127.0.0.1:5432/analytics
streamlit run main.py
```

Если Docker не используется, установите PostgreSQL 16 локально, создайте базу и
задайте DSN, например `postgresql://localhost/analytics`:

```bash
createdb analytics
export ANALYTICS_DATABASE_URL=postgresql://localhost/analytics
```

Для Homebrew PostgreSQL могут потребоваться полные пути к `createdb` и `psql`
из `/opt/homebrew/opt/postgresql@16/bin`. Схема создаётся автоматически при
первом подключении приложения (`schema.sql`).

Откройте `http://localhost:8501`. Администратор может загрузить CSV-файлы;
на новой установке база пуста. Для проверки зависимостей:

```bash
python -m pip check
python -c "import numpy, pandas, pyarrow; print(numpy.__version__, pandas.__version__, pyarrow.__version__)"
```

## Авторизация и сохранение входа при F5

После успешного входа браузер получает случайный токен сессии в cookie.
Сервер сохраняет только SHA-256-хэш токена, имя пользователя, отпечаток его
пароля и срок действия в PostgreSQL. Пароль и роль не передаются
в cookie: роль каждый раз берётся из серверной конфигурации.

- Вход сохраняется при F5, открытии другой вкладки этого сайта и перезапуске приложения.
- Сессия действует **7 дней с момента входа**. Обновление страницы не продлевает срок.
- Кнопка **«Выйти»** отзывает текущий токен на сервере и удаляет cookie. Повторное использование этого токена не даёт доступа.
- Смена пароля или удаление пользователя делает его прежние токены недействительными. После изменения файла пользователей перезапустите приложение.
- В браузере должны быть разрешены cookie для сайта. До их загрузки приложение показывает «Восстанавливаем сессию…».

Cookie имеет `Path=/` и `SameSite=Lax`; при HTTPS добавляется `Secure`.
Он устанавливается компонентом JavaScript и не имеет `HttpOnly`.
Для публичного размещения настройте HTTPS в обратном прокси.

### Настройка пользователей

Без `ANALYTICS_USERS_FILE` используются демонстрационные пользователи из
`access_control.py`. Для локальной проверки доступны «Администратор»
(`admin` / `admin123`) и роли `guest`, `analyst`, `developer`, `tester`.
На новом сервере установщик генерирует собственные случайные пароли для всех ролей.

Для внешней конфигурации задайте путь к JSON-файлу:

```bash
export ANALYTICS_USERS_FILE=/etc/analytics-team/users.json
```

Формат файла — словарь пользователей. `password_hash` — 64 шестнадцатеричных
символа SHA-256 пароля; пароль открытым текстом в этот файл не записывается.

```json
{
  "admin": {
    "password_hash": "<SHA256_ПАРОЛЯ: 64 шестнадцатеричных символа>",
    "role": "admin",
    "display_name": "Администратор"
  }
}
```

При заданной переменной этот файл **полностью заменяет** демонстрационные
учётные записи. Отсутствующий или некорректный файл не позволяет запустить
приложение. Поддерживаемые роли: `admin`, `guest`, `analyst`, `developer`, `tester`.
Получить хэш без помещения пароля в историю команд:

```bash
python - <<'PY_HASH'
import getpass, hashlib
print(hashlib.sha256(getpass.getpass('Пароль: ').encode()).hexdigest())
PY_HASH
```

### Пути к данным

| Переменная | Значение по умолчанию при локальном запуске | Назначение |
|------------|--------------------------------------------|------------|
| `ANALYTICS_DATABASE_URL` | Не задана | PostgreSQL: события и сессии авторизации |
| `DATABASE_URL` | Не задана | Запасной вариант, если `ANALYTICS_DATABASE_URL` не задан |
| `ANALYTICS_USERS_FILE` | Не задана | Внешние пользователи вместо демонстрационных |

Пароль PostgreSQL хранится только в окружении или в приватном env-файле и не
попадает в Git. Приложение создаёт таблицы `task_events` и `auth_sessions`,
если их ещё нет.

## Развёртывание на Ubuntu 24.04: systemd и Nginx

Скрипт `deploy/install.sh` воспроизводит использованный способ развёртывания:
отдельный служебный пользователь, Python venv, автозапуск, постоянные данные
и Nginx с поддержкой WebSocket. Он предназначен для **чистого сервера** с root-доступом.
Откройте входящие порты 22 и 80 в firewall провайдера.

На своём компьютере скачайте скрипт из репозитория и отправьте на новый сервер:

```bash
scp deploy/install.sh root@SERVER_IP:/root/analytics-install.sh
ssh root@SERVER_IP
bash /root/analytics-install.sh > /root/analytics-team-install.log 2>&1
tail -n 30 /root/analytics-team-install.log
```

Скрипт клонирует `main` и устанавливает зависимости из lock-файла. Для конкретной
версии задайте перед запуском `ANALYTICS_REF=<commit SHA или ветка>`.
Если `/opt/analytics-team` уже существует, скрипт остановится. Он отключает
стандартный сайт Nginx и делает приложение сайтом по умолчанию на порту 80:
на сервере с другими сайтами адаптируйте конфигурацию перед запуском.

| Назначение | Путь / адрес на сервере |
|------------|-------------------------|
| Исходники и venv | `/opt/analytics-team`, `/opt/analytics-team/.venv` |
| База аналитики и сессий | PostgreSQL `analytics`, роль `analytics_app` |
| Параметры подключения | `/etc/analytics-team/database.env` (root:analytics-team, 0640) |
| Пользователи | `/etc/analytics-team/users.json` (root:analytics-team, 0640) |
| Сгенерированные пароли | `/root/analytics-team-credentials.txt` (0600) |
| Служба | `/etc/systemd/system/analytics-team.service` |
| Nginx | `/etc/nginx/sites-available/analytics-team` |
| Streamlit | `127.0.0.1:8501`, доступен только внутри сервера |
| Внешний интерфейс | `http://SERVER_IP/` |

Откройте сайт, выберите «Администратор» и используйте сгенерированный пароль
`admin` из приватного файла на сервере. Это отдельный пароль приложения,
а не пароль SSH. Для HTTPS направьте домен на сервер и настройте сертификат
в Nginx. До настройки HTTPS можно использовать шифрованный SSH-туннель:

```bash
ssh -N -L 18501:127.0.0.1:8501 root@SERVER_IP
```

После подключения откройте `http://localhost:18501/`.

### Проверки и журналы

```bash
systemctl is-active analytics-team nginx
systemctl is-enabled analytics-team nginx
curl -f http://127.0.0.1:8501/_stcore/health
curl -f http://127.0.0.1/_stcore/health
journalctl -u analytics-team -n 100 --no-pager
nginx -t
```

Проверьте вход, отображение таблиц после загрузки CSV, F5 и выход.
Одного ответа `ok` от health endpoint недостаточно для проверки интерфейса.

### Обновление приложения

Перед обновлением сделайте резервную копию базы (см. ниже). Затем обновите код,
зависимости и схему:

```bash
set -a
. /etc/analytics-team/database.env
set +a
systemctl stop analytics-team
cd /opt/analytics-team
git fetch origin
git checkout --detach origin/main   # или конкретный commit SHA
.venv/bin/pip install --no-cache-dir -r requirements.lock.txt
psql "$ANALYTICS_DATABASE_URL" -v ON_ERROR_STOP=1 -f schema.sql
systemctl start analytics-team
systemctl status analytics-team --no-pager
```

Не удаляйте `/etc/analytics-team`: там хранятся DSN, пользователи и пароли.
Схема применяется идемпотентно, поэтому повторный запуск `schema.sql` безопасен.

### Резервная копия

Логический дамп PostgreSQL можно снимать без остановки приложения. Сохраните
также пользователей и точные версии зависимостей; храните архив приватно.

```bash
set -e
install -d -m 0700 /root/analytics-backups
set -a
. /etc/analytics-team/database.env
set +a
BACKUP="/root/analytics-backups/analytics-$(date +%F-%H%M%S).dump"
pg_dump --format=custom --file="$BACKUP" "$ANALYTICS_DATABASE_URL"
tar -czf "$BACKUP.users.tar.gz" -C / etc/analytics-team
chmod 0600 "$BACKUP" "$BACKUP.users.tar.gz"
```

Архив `*.users.tar.gz` содержит `database.env` с паролем PostgreSQL и
`users.json`, поэтому храните его так же строго, как сам дамп.
Восстановление: `pg_restore --dbname="$ANALYTICS_DATABASE_URL" "$BACKUP"` на
чистую базу. Перед восстановлением остановите приложение.

`data/` содержит Python-модули обработки задач и не является каталогом базы.
В Docker база хранится в named volume `pgdata`. Для production на Ubuntu выше
приведён проверенный путь systemd/Nginx.

---

## Формат входного CSV

Приложение ожидает CSV-файлы журнала изменений задач (экспорт из Jira/YouTrack/иной трекер). Обязательные колонки:

| Колонка | Описание | Пример |
|---------|----------|--------|
| `timestamp` | Дата/время события в формате ISO 8601 (строка) | `2024-01-15 10:30:00` |
| `changed_value` | Имя изменяемого поля | `Текущий статус`, `State`, `Приоритет по задаче`, `Дедлайн заказчика` |
| `added_values` | Новое значение поля | `В разработке`, `Критичный`, `1705312200000` |
| `removed_values` | Предыдущее значение поля | `К разработке`, `Обычный` |
| `author_full_name` | ФИО автора изменения | `Иванов Иван Иванович` |

Опциональные колонки:

| Колонка | Описание |
|---------|----------|
| `issue_id` | Внешний ID задачи (ключ) |
| `iissue_id` | Альтернативный ID задачи |
| `activity_type` | Тип активности (например, `IssueResolvedActivityItem`) |

### Пример минимального CSV

```csv
timestamp,changed_value,added_values,removed_values,author_full_name,issue_id
2024-01-15 09:00:00,Текущий статус,К разработке,Open,Петров П.П.,TASK-1
2024-01-15 10:00:00,Текущий статус,В разработке,К разработке,Иванов И.И.,TASK-1
2024-01-15 14:00:00,Текущий статус,К тестированию,В разработке,Иванов И.И.,TASK-1
2024-01-15 15:00:00,Текущий статус,В тестировании,К тестированию,Сидоров С.С.,TASK-1
2024-01-15 17:00:00,Текущий статус,Протестировано,В тестировании,Сидоров С.С.,TASK-1
```

### Поддерживаемые статусы (настраиваются в `config.py`)

- **Аналитика**: `К аналитике` → `В аналитике` → `К ревью (аналитика)` / `Ревью аналитики`
- **Разработка**: `К разработке` → `В разработке` → `К ревью (разработка)` / `Код ревью`
- **QA**: `К тестированию` → `В тестировании` → `Протестировано`
- **Завершение**: `К релизу`, `Релиз (установка доработок на боевой)`, `Завершено`

### Типы задач (распознаются автоматически)

В поле `changed_value` = `Type` / `Тип задачи в проекте` / `Тип работы` ожидаются значения:
- `Bug` / `Баг` → Дефект
- `Task` / `Задача` / `Change` / `Задача ОСФС` → Фича/Задача
- `Epic` / `Эпик` → Эпик
- `Техдолг` → Техдолг
- `Run` → Эксплуатация

### Приоритеты

Поле `changed_value` = `Приоритет по задаче` / `Priority`:
- `Блокирующий` → Блокирующий
- `Критичный` / `Critical` → Критичный
- `Важный` / `Major` → Важный
- `Обычный` / `Normal` → Обычный
- `Низкий` / `Minor` → Низкий

Поле `Приоритет в очереди` — числовой ранг в очереди.

### Оценки

Поля содержащие `оценка`, `size`, `storypoints` в `changed_value`:

**Новый формат (Оценка):**
- `Оценка аналитика план/факт`
- `Оценка разработка план/факт`
- `Оценка тестирование план/факт`

**Старый формат (StoryPoints) — также поддерживается:**
- `StoryPoints аналитика план/факт`
- `StoryPoints разработка план/факт`
- `StoryPoints тестирование план/факт`

**Общий размер задачи:**
- `Оценка задачи` / `Size` — T-shirt size (XS/S/M/L/XL) или числовые сторипоинты

Последнее значение по времени побеждает.

### Дедлайны

Поле `changed_value` = `Дедлайн заказчика` — значение в миллисекундах (ms since epoch).
Миллисекунды поддерживаются только для дедлайна; колонка `timestamp` должна
содержать дату/время ISO 8601, иначе событие будет пропущено как некорректное.

## Настройка команд (Core Teams)

Состав команд вынесен в `config/team.json`:

```json
{
  "core_qa_team": [
    "ФИО"
  ],
  "core_dev_team": [
    "ФИО"
  ],
  "core_analytics_team": [
    "ФИО"
  ]
}
```

Изменения вступают в силу после перезапуска приложения.

## Параметры в боковой панели

- **Начало/Конец дня** — рабочие часы (по умолчанию 9–18)
- **Обед + созвоны** — вычитаемые часы (по умолчанию 2.0)
- **База данных (PostgreSQL)** — статистика загруженных данных, кнопка очистки

## База данных (PostgreSQL)

Приложение использует **PostgreSQL 16** для постоянного хранения загруженных
CSV и сессий авторизации. Схема описана в `schema.sql`; приложение применяет её
идемпотентно при первом подключении.

### Дедупликация данных

На двух уровнях:

1. **Уровень файла** — MD5-хэш содержимого файла (`file_hash`). Если файл с таким хэшем уже загружен — пропускается полностью.
2. **Уровень строки** — SHA256-хэш бизнес-ключа (`row_hash`): `task_id|timestamp|changed_value|added_values|removed_values|author`. `INSERT ... ON CONFLICT (row_hash) DO NOTHING` гарантирует, что повторные загрузки не создают дубликаты.

### Перенос данных из прежней DuckDB

Остановите приложение, сделайте резервную копию файла DuckDB и задайте DSN
целевой базы PostgreSQL:

```bash
python -m pip install duckdb
export ANALYTICS_DATABASE_URL=postgresql://analytics:change-me@127.0.0.1:5432/analytics
python scripts/migrate_duckdb_to_postgres.py \
    --duckdb /var/lib/analytics-team/analytics.duckdb \
    --dsn "$ANALYTICS_DATABASE_URL"
```

Скрипт сохраняет исходные `row_hash` и `loaded_at`, поэтому повторная загрузка
тех же CSV не создаст дубликатов. Сессии входа не переносятся: после перехода
пользователям нужно войти заново.

### Сайдбар БД

- Метрики: всего строк, уникальных задач, загруженных файлов, последняя загрузка
- Кнопка **🗑️ Очистить базу** — полная очистка таблицы

## Вкладки аналитики

1. **🌐 Общая информация** — сквозная воронка, Lead Time, Flow Efficiency
2. **📅 Динамика по периодам** — группировка по месяцам или кварталам; задачи атрибутируются в период, в котором они были завершены (статусы `Протестировано` / `К релизу` / `Завершено`), незавершённые — отдельной строкой «В работе»
3. **🎯 Оценка задач** — план/факт по аналитике/разработке/QA, T-shirt size
   - **Калибровка T-Shirt размеров** — эталонные ориентиры по фактическим дням (P50, P85)
   - **Эффективность по факт-оценкам** — таблицы для QA / Dev / Analytics:
     - Фильтрация по Core Team (из `config/team.json`)
     - Детализация по сотрудникам: ФИО → отдельные таблицы по оценкам (XS/S/M/L/XL)
     - Колонки: Оценка факт, Задач (шт), Сумма дней, Среднее время (д.)
4. **⏰ Контроль дедлайнов (SLA)** — сдвиги дедлайнов, просрочки
5. **🐞 Дефекты vs Фичи** — распределение по типам, метрики по типам
6. **⚡ Приоритеты и Очереди** — время в очередях по приоритетам
7. **🧪 Аудит тестирования QA** — метрики QA, исполнители, реворки; при выборе периода итерации и метрики фильтруются по датам
8. **💻 Аудит разработки** — метрики Dev, код-ревью, исполнители; при выборе периода итерации и метрики фильтруются по датам
9. **📐 Аудит аналитики** — метрики Analytics, ревью требований; при выборе периода итерации и метрики фильтруются по датам
10. **🔍 Детализация по задаче** — таймлайн статусов конкретной задачи

## Структура проекта

```
├── main.py                 # Точка входа Streamlit
├── config.py               # Константы, статусы, загрузка team.json
├── config/
│   └── team.json           # Состав Core Teams (QA, Dev, Analytics)
├── auth.py                 # Вход, восстановление cookie, выход
├── auth_sessions.py        # PostgreSQL: выдача, проверка и отзыв токенов
├── db.py                   # PostgreSQL: загрузка, дедупликация, запросы
├── schema.sql              # Таблицы и индексы PostgreSQL
├── pyproject.toml          # Основные зависимости
├── requirements.lock.txt   # Зафиксированные версии всех зависимостей
├── Dockerfile              # Образ приложения
├── docker-compose.yml      # Приложение + PostgreSQL для локального запуска
├── .env.example            # Пример параметров PostgreSQL для Docker
├── deploy/install.sh       # Установка на чистую Ubuntu 24.04
├── scripts/                # Разовая миграция legacy-данных
├── README.md
├── data/
│   ├── pipeline.py         # Пакетная обработка; кэш стучится по отпечатку БД (get_db_fingerprint),
│   │                       # process_all_tasks — некэшированная обёртка для тестов
│   ├── task_processor.py   # Парсинг задач, расчёт фаз, оценок (Оценка + StoryPoints),
│   │                       # журнал интервалов ожидания QA («К тестированию»)
│   └── metrics.py          # Пересчёт метрик этапа (work/wait/rev/cycle/flow) по итерациям
│                           # и интервалам ожидания периода; очередь QA — из wait_df;
│                           # для Dev/Analytics — отдельные колонки wait и rev
├── utils/
│   ├── time_calc.py        # Векторизованный расчёт рабочих минут
│   └── stats.py            # Mean/Median/P85
├── ui/
│   ├── components.py       # UI-компоненты
│   ├── session_cookie/     # Компонент чтения и записи cookie
│   └── tabs/               # Рендереры вкладок
└── tests/                  # 104 теста
```

## Тестирование

```bash
python -m pip install pytest==8.3.5
test -f .env || cp .env.example .env
docker compose up -d db
docker compose exec db createdb -U analytics analytics_test || true
ANALYTICS_TEST_DATABASE_URL=postgresql://analytics:change-me@127.0.0.1:5432/analytics_test \
    python -m pytest tests/ -v
```

Если PostgreSQL установлен локально, создайте тестовую базу `analytics_test` и
используйте DSN вашего локального сервера, например
`postgresql://localhost:5432/analytics_test`.

Тесты очищают таблицы тестовой базы. `conftest.py` отказывается работать с базой,
в имени которой нет `test`, если явно не задан `ANALYTICS_ALLOW_UNSAFE_TEST_DB=1`.
Никогда не направляйте `ANALYTICS_TEST_DATABASE_URL` на production. В тестах
браузера cookie-компонент имитируется. F5 и выход дополнительно проверены в
Chrome на развёрнутом приложении.

### Набор тестов (104 теста)

| Файл | Тестов | Описание |
|------|--------|----------|
| `test_time_calc.py` | 12 | `get_work_minutes`: один день, границы рабочего времени, выходные, Mon-Fri, Mon-Mon, Fri-Mon, Sat-Mon, месяц, невалидные входы, кастомные часы, нулевой рабочий день |
| `test_stats.py` | 9 | `calc_stats`: пустая серия, None, нули, положительные, смешанные, отрицательные, одно значение, два значения, типы возврата |
| `test_validation.py` | 7 | `validate_csv_schema`: валидный минимальный, с опциональными, отсутствует 1/несколько колонок, пустой DF, case-sensitive, лишние колонки |
| `test_task_processor.py` | 30 | Парсинг: `clean_val`, `extract_task_type` (Bug/Task/Epic/Техдолг/Run/unknown), `extract_task_priorities` (RU/EN маппинг, очередь), `extract_task_estimates` (все роли, size), `extract_task_deadlines` (ms, on-time, no deadline, invalid, slippage), интеграция `process_single_task`: простой поток An→Dev→QA, детекция реворков (QA→Dev→QA), определение роли QA (core/non-core) |
| `test_pipeline.py` | 4 | `process_all_tasks`: две задачи, пустой DF, задача без статусов, изменение параметров рабочего дня |
| `test_metrics.py` | 14 | `recompute_role_period_metrics`: фильтрация итераций по периоду (внутри/вне/пересекает/пусто), пересчёт QA (нет итераций в периоде, одна итерация, смешанные периоды, очередь из wait_df, wait вне периода, без wait_df → 0), Dev (отдельные wait/rev), Analytics (отдельные wait/rev), неизвестная роль, пустой summary |
| `test_db.py` | 21 | PostgreSQL: row_hash (одинаковые/разные поля), file_hash, первая загрузка, дедуп по row_hash/file_hash, дубликаты внутри файла, NULL-поля, выборка по задачам, отпечаток, `is_file_loaded`, `get_all_events` (включая datetime-тип пустого результата), `get_summary_stats`, очистка БД |
| `test_ui_runtime.py` | 1 | Отображение таблицы Streamlit с NumPy, Pandas и PyArrow |
| `test_auth_sessions.py` | 4 | Сохранение токена между процессами, подделка, срок действия, смена пароля и отзыв |
| `test_auth_refresh.py` | 2 | Вход → новая сессия → выход, запрет повторного использования токена, ожидание cookie |

### Структура тестов

```
tests/
├── conftest.py              # sys.path и настройка тестовой PostgreSQL
├── test_auth_sessions.py
├── test_auth_refresh.py
├── test_ui_runtime.py
├── test_time_calc.py
├── test_stats.py
├── test_validation.py
├── test_task_processor.py
├── test_pipeline.py
├── test_metrics.py          # пересчёт метрик этапа за период
└── test_db.py               # тесты PostgreSQL дедупликации
```

Запуск с покрытием:
```bash
python -m pip install pytest-cov
ANALYTICS_TEST_DATABASE_URL=postgresql://analytics:change-me@127.0.0.1:5432/analytics_test \
    python -m pytest tests/ -v --cov=. --cov-report=term-missing
```
