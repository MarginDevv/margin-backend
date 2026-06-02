# Margin Backend

AI-управляющий для ресторанов: подключается к iikoCloud, считает реальную
маржинальность по чистой прибыли, находит утечки и ежедневно выдаёт
рекомендации.

## Стек

- Python 3.11 · FastAPI · Pydantic v2
- PostgreSQL 16 · SQLAlchemy 2.0 (async) · Alembic
- Celery + Celery Beat · Redis
- Docker Compose · Poetry
- Ruff · mypy · pytest (asyncio)

## Структура

```
app/
├── core/             # config, db, security, dependencies, logging, exceptions
├── api/v1/endpoints/ # FastAPI routers (auth, users, restaurants, integrations,
│                     # menu, analytics, recommendations, reports)
├── models/           # SQLAlchemy 2.0 models
├── schemas/          # Pydantic v2 schemas
├── repositories/     # Data-access layer
├── services/         # Business logic
│   ├── iiko/         # iikoCloud Transport API client, transformers, sync
│   ├── analytics/    # KPI, by-hour/day/weekday, dish performance, reports
│   └── recommendations/  # Heuristic engine producing daily recs
├── tasks/            # Celery app + tasks (iiko_sync, reports, recommendations)
├── utils/            # crypto (Fernet), datetime helpers
└── main.py
alembic/              # DB migrations
tests/                # unit + integration tests
```

## Быстрый старт (Docker)

```bash
cp .env.example .env
# обязательно задай APP_SECRET_KEY и JWT_SECRET_KEY длиной >= 16 символов

docker compose up --build
```

Сервисы:

| Сервис   | Порт | Назначение                              |
|----------|------|-----------------------------------------|
| api      | 8000 | FastAPI (Swagger: http://localhost:8000/docs) |
| postgres | 5432 | PostgreSQL                              |
| redis    | 6379 | Брокер + result backend                 |
| worker   | —    | Celery воркер                           |
| beat     | —    | Celery beat (планировщик)               |
| bot      | —    | Telegram-бот (aiogram, long-polling)    |

При первом запуске `api` сам прогоняет `alembic upgrade head`.

## Локально (без Docker)

```bash
poetry install
poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload
poetry run celery -A app.tasks.celery_app worker --loglevel=INFO
poetry run celery -A app.tasks.celery_app beat --loglevel=INFO
```

## Архитектурные решения

### Multi-tenant и роли
- `User` владеет `Restaurant` через таблицу `user_restaurant_roles` с ролью
  `owner | manager | staff`.
- Подписки привязаны к ресторану (1:1, `subscriptions.restaurant_id UNIQUE`).
- Любой защищённый эндпоинт берёт `restaurant_id` из path и через
  `require_owner / require_manager / require_member` проверяет роль.

### iiko integration
- `apiLogin` шифруется Fernet-ключом, производным от `APP_SECRET_KEY` (см.
  `app/utils/crypto.py`).
- `access_token` (TTL ~55 мин) кэшируется в `iiko_integrations`. Клиент
  автоматически переиздаёт его и повторяет запрос на 401.
- Транспорт: `httpx.AsyncClient` + `tenacity` (4 попытки, экспоненциальный
  бэкофф) для transient ошибок (5xx, сетевые сбои).

### Стратегия синхронизации
- **15 минут** — `incremental_sync_all` (Celery beat) фанит таски по всем
  активным интеграциям. Каждая тянет `documents/sales` с
  `dateFrom = last_sync_at − 10 минут`. Перекрытие защищает от пропусков.
- **04:00 локального TZ** — `daily_full_sync_all`: полная синхронизация
  номенклатуры + всех заказов за вчера (надёжность даже при сбоях
  инкрементального синка).
- Хранение детализировано: каждый `order_item` несёт цену, себестоимость и
  прибыль, заказ — `opened_at/closed_at`, по часам/дням недели аналитика
  считается из БД без перерасчёта в реальном времени.

### Daily report по графику ресторана
- В `Restaurant` есть `working_hours` (JSONB по дням недели, `HH:MM`) и
  `report_delay_minutes` (по умолчанию 60).
- Celery beat-таск `schedule_due_daily_reports` запускается каждые 15 мин и
  для каждого активного ресторана считает «close + delay» в его локальном
  TZ. Если момент попал в текущее 15-минутное окно — ставит цепочку
  `sync_day_then_build_daily(restaurant_id, business_day)`, которая сперва
  досинхронит заказы за бизнес-день (включая закрытия после полуночи),
  затем пересоберёт `Report`.
- Бизнес-день для смены, которая закрылась в 02:00 во вторник, = понедельник.
- Если у ресторана не настроены часы, работает safety-net — фановщик
  `build_daily_reports_all` в 05:00 берёт только их.

### Telegram-бот и web-дашборд
- Один digest = KPI отчёта + топ-3 рекомендации, отправляется во все Telegram-аккаунты,
  привязанные к ресторану, у которых `telegram_notifications=True`.
- Линковка: фронт получает `POST /users/me/telegram/link-token` → открывает
  `https://t.me/<bot>?start=<token>` → пользователь жмёт Start в Telegram →
  бот вызывает `TelegramLinkService.consume` и связывает chat_id с user_id.
  Токены живут 15 минут, single-use, refuse-on-duplicate-chat.
- Доставка идемпотентна: `telegram_deliveries` с UNIQUE
  `(restaurant_id, user_id, kind, for_date)` — повторные запуски не дублируют.
- Бот команды: `/start`, `/today`, `/yesterday`, `/help`, `/unlink`. При
  нескольких ресторанах — inline-кнопки выбора.
- **Два режима** работы, переключаются через `TELEGRAM_BOT_MODE` в env:
  - `polling` (по умолчанию, локалка и любой деплой без публичного URL).
    Запуск: `docker compose --profile polling up bot` — отдельный контейнер
    держит long-polling соединение с Telegram.
  - `webhook` (прод). Telegram сам POST-ит обновления на
    `POST /api/v1/webhooks/telegram/{secret}` твоего API. Контейнер `bot`
    не нужен — обновления обрабатывает `api`. Перед первым запуском один
    раз зарегистрируй URL: `docker compose --profile webhook-setup run --rm bot-setup`.
    Требуется задать `TELEGRAM_WEBHOOK_URL` (публичный HTTPS-origin) и
    `TELEGRAM_WEBHOOK_SECRET` (длинная случайная строка, проверяется и в URL,
    и в заголовке `X-Telegram-Bot-Api-Secret-Token`).
- Все ключевые события (sync ok/fail, отчёт собран, рекомендации сгенерированы,
  изменён статус рекомендации, отправлен digest, привязан/отвязан Telegram)
  пишутся в `activity_events` и доступны через
  `GET /restaurants/{id}/activity` — это лента для дашборда.

### On-demand отчёты с фронта
- `POST /api/v1/restaurants/{id}/reports/daily/build?for_date=YYYY-MM-DD`
  — manager+ кикает sync+rebuild. Возвращает `task_id` и `queued_at`.
- `POST /api/v1/restaurants/{id}/reports/weekly/build?week_start=YYYY-MM-DD`
  — то же для недели.

### Финансовая модель
- `MenuItem.margin_per_unit = sale_price * (1 − tax_rate) − food_cost`.
- `food_cost` считается **рекурсивно по техкартам iiko**
  (`product.assemblyCharts`): для составного блюда суммируются стоимости
  ингредиентов с учётом ингредиентов-полуфабрикатов на любую глубину. Если
  техкарты в номенклатуре нет — fallback на `costPrice` из iiko.
- `order_items.line_profit = line_revenue − unit_food_cost * quantity`.
- `orders.profit` = сумма `line_profit`. Все рекомендации и «лучший/худший
  день недели» считаются по `profit`, а не по выручке.

### Детектор утечек прибыли
- При полном дневном sync вместе с заказами тянем `documents/writeoffs`
  (списания) из iiko и кладём в таблицы `writeoffs` / `writeoff_items`.
- Если у аккаунта iiko этот endpoint недоступен — sync не падает, движок
  просто работает без данных по списаниям (рекомендация не сработает).
- В движке рекомендаций добавлена эвристика `INVENTORY_LEAK`: если за
  4 недели сумма списаний / чистая выручка > 5% — `HIGH`, > 8% — `CRITICAL`.
  Норма по отрасли 1–3%. В рекомендации перечисляются крупнейшие
  списанные позиции — куда смотреть в первую очередь.

### Рекомендации
Эвристический движок (`app/services/recommendations/engine.py`) на окне в
4 недели генерирует типы: `promote_dish`, `price_up`, `price_down`,
`remove_dish`, `cost_reduce`, `day_of_week`. Каждая запись несёт
`confidence` и `payload` со всеми входными цифрами для аудита.

## API (v1)

```
POST /api/v1/auth/register          — owner + первый ресторан
POST /api/v1/auth/login             — JWT access + refresh
POST /api/v1/auth/refresh

GET  /api/v1/users/me               — профиль
PATCH /api/v1/users/me
POST /api/v1/users/me/password

GET  /api/v1/restaurants            — мои рестораны
POST /api/v1/restaurants
GET  /api/v1/restaurants/{id}
PATCH /api/v1/restaurants/{id}      [owner]
GET  /api/v1/restaurants/{id}/members              [owner]
POST /api/v1/restaurants/{id}/members              [owner]
DELETE /api/v1/restaurants/{id}/members/{user_id}  [owner]

POST   /api/v1/restaurants/{id}/integrations/iiko       [owner]
GET    /api/v1/restaurants/{id}/integrations/iiko       [manager+]
PATCH  /api/v1/restaurants/{id}/integrations/iiko       [owner]
DELETE /api/v1/restaurants/{id}/integrations/iiko       [owner]
POST   /api/v1/restaurants/{id}/integrations/iiko/sync  [manager+]  ?full=true

GET   /api/v1/restaurants/{id}/menu               [member+]
PATCH /api/v1/restaurants/{id}/menu/{menu_item_id}[manager+]

GET /api/v1/restaurants/{id}/analytics/kpi         [member+]
GET /api/v1/restaurants/{id}/analytics/by-hour     [member+]
GET /api/v1/restaurants/{id}/analytics/by-day      [member+]
GET /api/v1/restaurants/{id}/analytics/by-weekday  [member+]
GET /api/v1/restaurants/{id}/analytics/dishes?sort_by=qty|revenue|profit|margin_percent       [member+]
GET /api/v1/restaurants/{id}/analytics/dishes/ranked?sort_by=...&direction=asc|desc&limit=...  [member+]
GET /api/v1/restaurants/{id}/analytics/dishes/daily?menu_item_id=...                           [member+]
GET /api/v1/restaurants/{id}/analytics/dishes/{menu_item_id}/trend?granularity=day|week        [member+]
GET /api/v1/restaurants/{id}/analytics/categories                                              [member+]
GET /api/v1/restaurants/{id}/analytics/cross-sell?min_orders=2&limit=20                        [member+]

GET   /api/v1/restaurants/{id}/recommendations             [member+]
PATCH /api/v1/restaurants/{id}/recommendations/{rec_id}    [manager+]

GET  /api/v1/restaurants/{id}/reports/daily?for_date=YYYY-MM-DD     [member+]
GET  /api/v1/restaurants/{id}/reports/weekly?week_start=YYYY-MM-DD  [member+]
POST /api/v1/restaurants/{id}/reports/daily/build?for_date=YYYY-MM-DD     [manager+]
POST /api/v1/restaurants/{id}/reports/weekly/build?week_start=YYYY-MM-DD  [manager+]
POST /api/v1/restaurants/{id}/reports/daily/deliver?for_date=YYYY-MM-DD   [manager+]

GET    /api/v1/users/me/telegram/status                              — TG-статус привязки
POST   /api/v1/users/me/telegram/link-token                          — deep-link для связки
DELETE /api/v1/users/me/telegram                                     — отвязать TG
GET    /api/v1/users/me/telegram/notifications/{restaurant_id}       [member+]
PATCH  /api/v1/users/me/telegram/notifications/{restaurant_id}       [member+] — toggle

GET /api/v1/restaurants/{id}/activity?kind=...&severity_at_least=... [member+]

GET /api/v1/users/me/referral                                        — мой код + сводка
GET /api/v1/users/me/referral/payouts?status=...                     — начисления комиссий
```

## Реферальная программа

- У каждого пользователя есть `referral_code` (8 символов, без 0/O/1/I/L).
  Код выдаётся лениво при первом обращении к `GET /users/me/referral`.
- При регистрации (`/auth/register`) или создании нового ресторана
  (`POST /restaurants`) можно передать `referral_code`. Реферер привязывается
  к ресторану один раз и навсегда (`restaurants.referrer_user_id`).
- Каждое успешное закрытие инвойса по подписке создаёт строку
  `referral_payouts` со статусом `pending` и комиссией 10% (`commission_rate`
  настраивается в `accrue_for_invoice`). Дальше — модуль биллинга проводит
  выплаты (`approved` → `paid`).
- Эндпоинт `GET /users/me/referral` отдаёт сводку: код, deep-link, число
  приведённых ресторанов, накопленную и выплаченную комиссию.

## LLM (российские провайдеры)

- **GigaChat** (Сбер) и **YandexGPT** — два встроенных провайдера, выбор через
  `LLM_PROVIDER` в env. Пустое значение → шаблонный движок без LLM.
- Эвристический движок рекомендаций решает **что** советовать
  (с точными числами); LLM перерабатывает описание и формулировку действия
  в естественный деловой русский — числа и факты сохраняются. Любая ошибка
  LLM → fallback на шаблонный текст, рекомендация всё равно создаётся.
- Интерфейс `LLMClient` универсальный — добавить новый провайдер = один файл
  в `app/services/llm/`.

## Команды

```bash
poetry run ruff check .
poetry run ruff format .
poetry run mypy app
poetry run pytest

poetry run alembic revision --autogenerate -m "..."
poetry run alembic upgrade head
```

## Roadmap (вне MVP)

- Sync ассемблейных карт iiko для точного food_cost (сейчас fallback на `costPrice`).
- Полная доставка ежедневных рекомендаций в Telegram (`TELEGRAM_BOT_TOKEN` в env).
- Биллинг подписок (Stripe / ЮKassa / CloudPayments).
- Webhook-приём событий iiko как опциональная альтернатива пуллингу.
- Rate-limit и audit-log на API.
