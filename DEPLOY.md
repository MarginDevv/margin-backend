# Деплой Margin Backend на VPS (Ubuntu 24.04)

Пошаговая инструкция от пустого сервера до работающего бота. Рассчитана на
Beget Облако / любой VPS с Ubuntu 24.04 и root-доступом. Все команды для
shell на сервере, если не указано иное.

> **Время на всё:** 20–30 минут. Уровень: новичок (копируй и вставляй).

---

## 0. Что должно быть у тебя ДО старта

- [ ] VPS создан, у тебя есть **IP-адрес** (например, `5.187.0.42`) и **пароль root** (или SSH-ключ).
- [ ] Новый **токен бота** от @BotFather (старый отозван).
- [ ] **Username бота** без `@` (например, `margin_money_bot`).
- [ ] Терминал на твоём компьютере (Terminal на macOS / PowerShell на Windows / любой).

Если используешь Windows и нет SSH — поставь Git for Windows (внутри есть `ssh.exe`) или Windows Terminal с OpenSSH.

---

## 1. Подключаемся к серверу

В терминале на твоём компе:

```bash
ssh root@5.187.0.42
```

Заменишь `5.187.0.42` на свой IP. Первый раз спросит про fingerprint — отвечай `yes`. Введи пароль (символы не отображаются — это нормально).

Если зашёл — увидишь приглашение типа `root@server:~#`. Всё дальше — на сервере.

### Сменить пароль root (если ставил слабый)

```bash
passwd
```

---

## 2. Базовая настройка системы

```bash
# Обновить пакеты
apt update && apt upgrade -y

# Поставить полезное
apt install -y curl git ufw fail2ban htop nano
```

### Firewall

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
ufw status
```

Открываем только SSH (22), HTTP (80) и HTTPS (443). Порт API (8000) **наружу не выставляем** — позже его закроет reverse-proxy.

---

## 3. Устанавливаем Docker

Официальный скрипт от Docker:

```bash
curl -fsSL https://get.docker.com | sh
```

Проверь:

```bash
docker --version
docker compose version
```

Должно показать версии. Если ошибка — повтори команду установки.

---

## 4. Клонируем репозиторий

```bash
cd /opt
git clone https://github.com/MarginDevv/margin-backend.git
cd margin-backend
```

(Когда выйдешь из ветки `claude/eager-gauss-XEmJR` в `main` — клонируй из `main`.)

---

## 5. Создаём `.env` с секретами

```bash
cp .env.example .env
nano .env
```

В редакторе `nano` подставь свои значения. Ниже минимальный набор, который **обязательно** надо изменить:

```env
# --- ПРИЛОЖЕНИЕ ---
APP_ENV=production
APP_DEBUG=false
APP_BASE_URL=http://5.187.0.42:8000           # пока IP, потом домен
# Сгенерируй: openssl rand -hex 32
APP_SECRET_KEY=ВСТАВЬ_СЮДА_СЛУЧАЙНУЮ_СТРОКУ_64_СИМВОЛА
JWT_SECRET_KEY=ВСТАВЬ_СЮДА_ДРУГУЮ_СЛУЧАЙНУЮ_СТРОКУ_64_СИМВОЛА

# --- POSTGRES (придумай надёжный пароль) ---
POSTGRES_PASSWORD=надёжный_пароль_от_базы
# Если используешь managed-Postgres от Supabase вместо локального контейнера —
# скопируй Session Pooler URI из Project Settings → Database, замени схему
# postgresql:// → postgresql+asyncpg:// и убери ?pgbouncer=true:
# DATABASE_URL=postgresql+asyncpg://postgres.<ref>:<password>@aws-0-eu-west-1.pooler.supabase.com:5432/postgres
# Бэкенд ходит ролью `postgres` (BYPASSRLS), миграция 0011 закрывает PostgREST.

# --- TELEGRAM ---
TELEGRAM_BOT_TOKEN=новый_токен_от_BotFather
TELEGRAM_BOT_USERNAME=margin_money_bot
TELEGRAM_BOT_MODE=polling
APP_BASE_URL=                                  # позже впишешь, когда будет домен
```

Сгенерировать секреты прямо на сервере:

```bash
openssl rand -hex 32      # ← это для APP_SECRET_KEY
openssl rand -hex 32      # ← это для JWT_SECRET_KEY
```

Выходим из `nano`: **Ctrl+O** (сохранить) → Enter → **Ctrl+X** (выйти).

Проверь, что `.env` не пустой и не в git:

```bash
git status               # .env не должен быть в списке
ls -la .env              # файл существует
```

---

## 6. Запускаем

```bash
docker compose --profile polling up -d
```

`-d` = detached (в фоне). Сборка образов в первый раз займёт ~3–5 минут.

Проверь, что всё поднялось:

```bash
docker compose ps
```

Должны быть `Up` или `running`:
- `margin-postgres` (healthy)
- `margin-redis` (healthy)
- `margin-api`
- `margin-worker`
- `margin-beat`
- `margin-bot`

Посмотреть логи любого сервиса:

```bash
docker compose logs -f api          # API
docker compose logs -f bot          # бот
docker compose logs -f worker       # фоновые задачи
```

`Ctrl+C` — выйти из логов (контейнеры продолжают работать).

---

## 7. Проверь, что работает

### API

```bash
curl http://localhost:8000/health
# Ожидаем: {"status":"ok","env":"production"}
```

С другого компьютера:

```bash
curl http://5.187.0.42:8000/health
```

Если не отвечает — проверь, что 8000 порт открыт (для теста можно временно
`ufw allow 8000/tcp`; в проде закроем за nginx).

Swagger: открой в браузере `http://5.187.0.42:8000/docs`.

### Бот

Открой в Telegram `@margin_money_bot` (или твоё имя), напиши `/help`.
Должен ответить справкой. Если молчит:

```bash
docker compose logs bot | tail -50
```

Типичные проблемы:
- **Unauthorized** → токен битый или старый. Сгенерируй новый в @BotFather.
- **Conflict: terminated by other getUpdates request** → где-то ещё запущен бот с тем же токеном. Останови.

---

## 8. Автозапуск при перезагрузке VPS

Docker сам стартует с системой (после `get.docker.com`). Контейнеры с
`restart: unless-stopped` поднимутся автоматически. Но если хочется
жёсткой гарантии — systemd-unit:

```bash
cat > /etc/systemd/system/margin.service <<'EOF'
[Unit]
Description=Margin backend (docker compose)
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/margin-backend
ExecStart=/usr/bin/docker compose --profile polling up -d
ExecStop=/usr/bin/docker compose --profile polling down

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable margin.service
systemctl start margin.service
```

Проверь:

```bash
systemctl status margin
```

---

## 9. Обновление кода (когда я залью новые коммиты)

```bash
cd /opt/margin-backend
git pull
docker compose --profile polling up -d --build
```

Миграции БД (`alembic upgrade head`) применятся автоматически при старте `api`.

---

## 10. Бэкап базы (раз в день)

```bash
mkdir -p /opt/margin-backups

cat > /etc/cron.daily/margin-backup <<'EOF'
#!/bin/sh
TS=$(date +%Y%m%d_%H%M%S)
docker exec margin-postgres pg_dump -U margin margin | gzip > /opt/margin-backups/margin_${TS}.sql.gz
# держим только последние 14 дней
find /opt/margin-backups -name 'margin_*.sql.gz' -mtime +14 -delete
EOF

chmod +x /etc/cron.daily/margin-backup
```

Beget Облако ещё и сам делает автобэкапы VPS, как страховка.

---

## 11. Дальше: домен + webhook + HTTPS

Когда захочешь перейти с polling на webhook (и/или подключить фронт-дашборд):

1. Купи домен (любой регистратор) или субдомен.
2. В DNS пропиши **A-запись** `api.твой-домен.ру` → IP сервера.
3. Поставь Caddy — это reverse-proxy с автоматическим Let's Encrypt:

```bash
apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor -o /usr/share/keyrings/caddy.gpg
echo "deb [signed-by=/usr/share/keyrings/caddy.gpg] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main" > /etc/apt/sources.list.d/caddy.list
apt update && apt install -y caddy
```

4. Конфиг:

```bash
cat > /etc/caddy/Caddyfile <<'EOF'
api.твой-домен.ру {
    reverse_proxy localhost:8000
}
EOF

systemctl reload caddy
```

5. В `.env`:

```env
TELEGRAM_BOT_MODE=webhook
TELEGRAM_WEBHOOK_URL=https://api.твой-домен.ру
TELEGRAM_WEBHOOK_SECRET=сгенерируй_openssl_rand_hex_32
APP_BASE_URL=https://app.твой-домен.ру       # если будет отдельный фронт
```

6. Перезапусти и зарегистрируй webhook:

```bash
docker compose --profile polling down                  # выключить polling-бот
docker compose up -d api worker beat                   # без бота
docker compose --profile webhook-setup run --rm bot-setup   # зарегистрировать webhook
```

7. Закрой UFW для порта 8000:

```bash
ufw delete allow 8000/tcp 2>/dev/null
ufw reload
```

Теперь Telegram пушит обновления в `https://api.твой-домен.ру/api/v1/webhooks/telegram/{secret}`, Caddy проксирует на 8000.

---

## Что делать если что-то сломалось

```bash
# Глянуть последние ошибки во всех контейнерах
docker compose logs --since=10m

# Перезапустить
docker compose --profile polling restart

# Полный рестарт
docker compose --profile polling down
docker compose --profile polling up -d

# Войти в контейнер посмотреть изнутри
docker exec -it margin-api bash

# Войти в psql
docker exec -it margin-postgres psql -U margin -d margin
```

Если совсем застрял — пришли мне последние 50 строк лога нужного сервиса.
