# iikoCloud Transport API — OpenAPI specification

`iiko_openapi.json` — официальная OpenAPI 3.0.1 спецификация iikoCloud
Transport API. Скачана с https://api-ru.iiko.services/docs (страница
рендерится через Redocly; «Download OpenAPI specification» в правом верхнем
углу отдаёт этот файл).

## Зачем коммитим спек в репо

1. **Source of truth для код-ревью.** Любые изменения в
   `app/services/iiko/*` теперь можно сверять с конкретным разделом
   спека — без догадок и без зависимости от доступности сайта iiko.

2. **Воспроизводимость.** Версия API, против которой написан наш код,
   зафиксирована в git. Если iiko опубликует breaking change, мы это
   увидим через diff при обновлении.

3. **Автогенерация (потенциально).** Спек можно скармливать
   `openapi-python-client` / `datamodel-code-generator`, чтобы родить
   типизированные модели запросов/ответов. Пока этого не делаем —
   текущий клиент тонкий и ручной.

## Как обновлять

1. Открой https://api-ru.iiko.services/docs в браузере.
2. Кнопка «Download OpenAPI specification».
3. Замени `docs/iiko_openapi.json` новым файлом.
4. Сделай `git diff docs/iiko_openapi.json` и проверь breaking changes
   для тех эндпоинтов, которые мы используем (см. `app/services/iiko/client.py`).

## Что в спеке (для быстрой навигации)

- **131 эндпоинт** в 7 группах: Authorization, Organizations, Terminal
  groups, Dictionaries, Menu, Operations, Employees, Deliveries
  (Create/Retrieve), Orders, Banquets/reserves, Webhooks, Loyalty.
- **Auth:** `/api/1/access_token` (deprecated) → `/api/v2/access_token`.
- **Menu:** `/api/1/nomenclature` — главный источник продуктов и
  computed cost. Recipe-эндпоинтов в этом API **нет** — рецептуры
  живут только в iikoRMS (on-premise).
- **Orders / sales:** Transport API различает **delivery orders**
  (`/api/1/deliveries/*`) и **table orders** (`/api/1/order/*`). Нет
  одного эндпоинта, который вернёт «все закрытые чеки за период».
