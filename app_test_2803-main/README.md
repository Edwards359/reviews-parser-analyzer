# Reviews App

Сервис отзывов: FastAPI + PostgreSQL + SQLAlchemy async, миграции Alembic.

## Ключевые возможности

- Публичное API (с rate-limit и дедупликацией повторных отправок) для приёма отзывов и ответов пользователей.
- Служебное API (`/api/v1/reviews/claim`, `/api/v1/reviews/ai-reply`, `PATCH /api/v1/reviews/{id}`) под заголовком `X-Worker-Token` — только для worker.
- Флаг `is_ai` у записей: помогает worker’у корректно фильтровать собственные ответы.
- Атомарный «claim» через `SELECT ... FOR UPDATE SKIP LOCKED` (`new → processing → processed/failed`) — несколько worker-инстансов не конфликтуют.
- Webhook приложения → worker: о новом отзыве сообщается сразу, без ожидания опроса.
- Health-эндпоинты `/healthz` и `/readyz` (проверяет БД).
- Correlation-id во всех логах через middleware.
- CSV-экспорт отзывов (`GET /api/v1/reviews.csv`).
- UI с пометкой «AI» у сообщений ассистента и расширенным набором статусов.

## Запуск

```bash
cp .env.example .env  # заполнить WORKER_API_TOKEN (>=16 символов)
docker compose up --build -d
```

Контейнер при старте прогоняет миграции Alembic (`alembic upgrade head`).

Единый compose для обоих сервисов — в корне репозитория (`../docker-compose.yml`), worker запускается через `--profile worker`.

## Безопасность

- Токен в `.env` должен быть случайной строкой длиной не меньше 16 символов. Для локальных экспериментов можно выставить `ALLOW_INSECURE_TOKEN=true`.
- Публичный POST ограничен rate-limit’ом (`PUBLIC_RATE_LIMIT_PER_MINUTE`).
- Авторство «AI» проставляется только служебным эндпоинтом: клиент не может подделать роль ИИ.
