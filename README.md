# Reviews: парсер и анализатор

[![CI](https://github.com/Edwards359/reviews-parser-analyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/Edwards359/reviews-parser-analyzer/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Два сервиса в одном репозитории.

- `app_test_2803-main/` — веб-приложение на FastAPI: хранит отзывы, отдаёт API и UI.
- `worker_ai-main/` — фоновый ассистент: забирает новые отзывы, определяет тональность, генерирует ответ через LLM (OpenAI / GigaChat / YandexGPT) и публикует его в приложении.

## Ключевые особенности реализации

1. **Безопасность API.** Служебный эндпоинт `/api/v1/reviews/ai-reply` под `X-Worker-Token`; флаг `is_ai` ставит сервер, клиент не может подделать «AI»; публичный POST защищён rate-limit и дедупом.
2. **Атомарный claim.** Новый эндпоинт `/api/v1/reviews/claim` использует `FOR UPDATE SKIP LOCKED`; статусы `new → processing → processed/failed` — несколько worker-инстансов не конфликтуют.
3. **Миграции Alembic.** Схема БД ведётся миграциями; при старте контейнера прогоняется `alembic upgrade head`.
4. **Модульные LLM-провайдеры.** Под общий интерфейс `LLMProvider` реализованы `OpenAI`, `GigaChat`, `YandexGPT`, `Fallback`. Переключение через `LLM_PROVIDER`.
5. **Структурированный ответ LLM.** Единый JSON `{tone, reply}` — одним вызовом и тональность, и ответ.
6. **Ретраи.** `tenacity` вокруг сетевых вызовов (приложение и LLM).
7. **Push вместо опроса.** Webhook от приложения к worker (`/webhook/review-created`) разблокирует цикл, polling остался как fallback.
8. **Наблюдаемость.** Correlation-id middleware, health-эндпоинты `/healthz`, `/readyz`.
9. **UI-улучшения.** Бейдж `AI`, расширенные статусы, устойчивость к будущим значениям.
10. **Docker.** Multi-stage сборка, non-root пользователь, `HEALTHCHECK`, единый `docker-compose.yml` с профилями.
11. **Тесты.** `pytest` на `tone`, `parse_llm_response`, `state`.

## Быстрый запуск (Docker)

```bash
cp app_test_2803-main/.env.example app_test_2803-main/.env
cp worker_ai-main/.env.example worker_ai-main/.env
# выставить WORKER_API_TOKEN одинаковым в обоих .env

docker compose up --build -d               # только приложение + БД
docker compose --profile worker up --build -d   # + worker
```

Открыть `http://127.0.0.1:8000/`.

## Локальная разработка

Целевой интерпретатор — **Python 3.12** (тот же, что и в Docker-образе `python:3.12-slim`).
Зафиксирован в `.python-version` и `pyproject.toml`. На 3.12 есть готовые wheels для
всех используемых библиотек (SQLAlchemy 2, asyncpg, psycopg, pydantic-core, openai,
httpx, tenacity, alembic) — установка не требует компиляции.

Создать venv и поставить все зависимости:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r app_test_2803-main\requirements.txt -r worker_ai-main\requirements.txt pytest pytest-asyncio ruff mypy python-docx docx2pdf
```

Проверка:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\ -q
.\.venv\Scripts\python.exe -m ruff check app_test_2803-main worker_ai-main tests
```

## Структура

```text
app_test_2803-main/   # FastAPI, PostgreSQL, Alembic
worker_ai-main/       # worker + LLM провайдеры + webhook-сервер
tests/                # pytest
docker-compose.yml    # единый compose (web+db, worker по профилю)
pyproject.toml        # ruff / pytest / mypy
```
