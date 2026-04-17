# Worker Service

Фоновый сервис обработки отзывов. Живёт отдельно от приложения и БД, обращается к сайту по HTTP.

## Что делает сервис

- Периодически (или по webhook-триггеру от приложения) вызывает `POST /api/v1/reviews/claim` и атомарно забирает новые отзывы (`new → processing`).
- Для каждого отзыва определяет тональность и генерирует ответ через выбранный LLM-провайдер (OpenAI / GigaChat / YandexGPT) или через fallback-словарь при отсутствии ключей.
- Создаёт на сайте отдельный комментарий-ответ через служебный `POST /api/v1/reviews/ai-reply` (флаг `is_ai=True` ставится сервером).
- Помечает исходный отзыв как `processed` и записывает в него `tone` и `response`.
- Отправляет уведомление о новом отзыве в Telegram (если сконфигурировано).
- Поднимает внутренний webhook-сервер (`/webhook/review-created`) и разблокирует цикл опроса сразу при получении события от приложения.

## Файлы

- `config.py` — настройки через `.env`.
- `client.py` — HTTP-клиент (с ретраями `tenacity`) для claim / ai-reply / patch.
- `models.py` — Pydantic-модели worker.
- `tone.py` — словарный классификатор с поддержкой отрицаний («не понравилось»).
- `providers/` — реализации LLM: `OpenAIProvider`, `GigaChatProvider`, `YandexGPTProvider`, `FallbackProvider`. Выбор через `LLM_PROVIDER`.
- `processor.py` — обёртка над провайдером с fallback при сбоях.
- `state.py` — локальный JSON для идемпотентности Telegram-уведомлений.
- `telegram_bot.py` — отправка уведомлений.
- `webhook_server.py` — HTTP-сервер (FastAPI) для push-триггера от приложения.
- `worker.py` — основной цикл.
- `requirements.txt`, `Dockerfile`, `docker-compose.yml`.

## Настройки

Минимум: `TARGET_SITE_URL`, `WORKER_API_TOKEN` (совпадает с токеном приложения), `LLM_PROVIDER` + соответствующие ключи.

Пример — см. `.env.example`.

## Запуск

```bash
cp .env.example .env  # заполнить значения
docker compose up --build -d
```

Или локально:

```bash
pip install -r requirements.txt
python worker.py
```

## Webhook

Приложение само дергает `POST /webhook/review-created` на worker, чтобы не ждать интервал опроса. Polling остаётся как fallback.

## Telegram

1. Создайте бота через `@BotFather`.
2. В `.env` укажите `TELEGRAM_BOT_TOKEN` и `TELEGRAM_USER_CHAT_ID`.
3. Если Telegram не сконфигурирован — worker продолжает работу без уведомлений.
