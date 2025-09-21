# PingTower — запуск проекта (коротко и понятно)

Мониторинг доступности и задержек с API и простой UI.

## Быстрый старт (Windows, без Docker, SQLite)

Запуск в PowerShell из каталога репозитория:

```
cd MAINPROJECT
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt

# Используем SQLite, чтобы ничего не устанавливать
$env:DB_URL="sqlite+pysqlite:///./data.sqlite"
$env:CLICKHOUSE_ENABLE="false"

# Запуск API (UI доступен на /)
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Проверка:

```
curl http://127.0.0.1:8000/health
# Открой в браузере: http://127.0.0.1:8000/
# Метрики Prometheus: http://127.0.0.1:8000/metrics
# Готовность: http://127.0.0.1:8000/ready
```

Если порт занят, укажи другой: `--port 8010`.

## Полный стек через Docker Compose (web + Postgres [+ ClickHouse])

Требуется установленный Docker Desktop.

1) Создай файл `.env` в `MAINPROJECT/` (минимум):
```
APP_PORT=8000
DB_URL=postgresql+psycopg://user:password@postgres:5432/fastapi_db
CLICKHOUSE_ENABLE=false
LOG_LEVEL=INFO
LOG_JSON=false
API_KEY=
```
2) Запуск:
```
docker compose -f MAINPROJECT/docker-compose.yml up -d
```
3) Проверка:
- http://localhost:8000/health
- http://localhost:8000/
- http://localhost:8000/metrics
- http://localhost:8000/ready

Чтобы включить ClickHouse, задай `CLICKHOUSE_ENABLE=true` и при необходимости параметры подключения (`CLICKHOUSE_URL`, `CLICKHOUSE_DB`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`).

## Нативный запуск с PostgreSQL (без Docker)

1) Установи PostgreSQL локально, создай БД (пример):
- DB: `fastapi_db`
- USER/PASSWORD: `user`/`password`

2) Активируй виртуальную среду и зависимости:
```
cd MAINPROJECT
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

3) Запусти API с Postgres:
```
$env:DB_URL="postgresql+psycopg://user:password@localhost:5432/fastapi_db"
$env:CLICKHOUSE_ENABLE="false"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## API кратко

- GET `/health` → `{ "status": "ok" }`
- GET `/services`
- POST `/services` (body: `{ "name": "Site A", "url": "https://example.com", "interval_s": 60, "timeout_s": 5 }`)
- GET `/status/{id}`
- GET `/services/{id}/history?limit=100`
- POST `/services/{id}/recheck` (async queue)
- GET `/incidents?open=true`

Правила валидации:
- `url` только `http`/`https`
- `interval_s >= 60`
- `timeout_s >= 1`

Авторизация на изменяющих эндпоинтах (POST/PUT/DELETE):
- Задай `API_KEY` в окружении
- Передавай заголовок: `X-API-KEY: <твой_ключ>`

## Частые проблемы

- 500 на `/services` при старте: задан Postgres по умолчанию, а он недоступен. Для локального старта задай
  `$env:DB_URL="sqlite+pysqlite:///./data.sqlite"` и перезапусти API.
- 503 на `/ready`: БД/планировщик ещё не готовы. Убедись, что `DB_URL` валиден, подожди несколько секунд.
- Порт занят: добавь `--port 8010`.

## Полезные переменные окружения

- APP_PORT, DB_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, CHECK_TICK_SEC
- GLOBAL_CONCURRENCY, GLOBAL_RPS
- HTTP_CONNECT_TIMEOUT_SEC, HTTP_READ_TIMEOUT_SEC, HTTP_SSL_VERIFY, HTTP_SSL_INSECURE_RETRY, HTTP_CA_BUNDLE
- URL_ALLOW_REGEX, URL_DENY_REGEX
- API_KEY, WEBHOOK_URL
- LOG_LEVEL, LOG_JSON
- RATE_LIMIT_ENABLE, RATE_LIMIT_PER_MIN, RATE_LIMIT_BURST
- CLICKHOUSE_ENABLE, CLICKHOUSE_URL, CLICKHOUSE_DB, CLICKHOUSE_USER, CLICKHOUSE_PASSWORD 