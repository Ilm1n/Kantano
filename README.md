# Kantano (LightTask)

Kantano - lightweight Kanban task manager на `FastAPI + Vue + PostgreSQL`.

Посмотреть - [Kantano.ru](https://kantano.ru)

## Содержание
- [1. Что это](#1-что-это)
- [2. Архитектура](#2-архитектура)
- [3. Структура репозитория](#3-структура-репозитория)
- [4. Быстрый старт (Development)](#4-быстрый-старт-development)
- [5. Переменные окружения (.env)](#5-переменные-окружения-env)
- [6. JWT ключи (`certs`)](#6-jwt-ключи-certs)
- [7. Caddy / Swagger пароль](#7-caddy--swagger-пароль)
- [8. Деплой (Production)](#8-деплой-production)
- [9. Полезные команды](#9-полезные-команды)
- [10. Документация проекта](#10-документация-проекта)
- [11. Troubleshooting](#11-troubleshooting)

## 1. Что это
Основные возможности:
- регистрация/логин с JWT (`access` + `refresh` cookie)
- вход через Yandex ID как дополнительный способ авторизации
- проекты и роли (`OWNER`, `MANAGER`, `MEMBER`)
- Kanban board: колонки, задачи, drag-and-drop
- теги, исполнители, приоритеты, фильтрация
- инвайты в проект (invite links + QR)
- аватары пользователей в локальном dev-storage или S3-compatible storage

## 2. Архитектура
Production topology:
- `gateway` (`Caddy`) раздаёт frontend и проксирует `/api/*` в backend
- `backend` (`FastAPI + SQLAlchemy async + Alembic`)
- `db` (`PostgreSQL`)
- `redis` (`Redis Pub/Sub` для realtime fanout + presence)

Development topology:
- `db + redis + backend` поднимаются через `docker-compose.dev.yml`
- frontend обычно запускается локально через `pnpm dev`

## 3. Структура репозитория
```text
.
├── backend/light_task/              # FastAPI backend + Alembic + Dockerfile
├── frontend/light-task-frontend/    # Vue 3 frontend + Vite + Pinia
├── docker-compose.dev.yml           # Dev окружение (db + redis + backend)
├── docker-compose.prod.yml          # Prod окружение (gateway + backend + db + redis)
├── Caddyfile                        # Gateway config + basic auth для docs
├── .env.template                    # Шаблон .env для development
├── .env.prod.template               # Шаблон .env для ручного production deploy
├── .github/workflows/deploy.yml     # GitHub Actions deploy pipeline
└── docs/project-audit/              # Подробный аудит и контекст системы
```

## 4. Быстрый старт (Development)
### 4.1 Требования
- Docker + Docker Compose
- Node.js LTS + `pnpm`

### 4.2 Подготовка `.env`
```bash
cp .env.template .env
```
Заполни обязательные значения для DB.

### 4.3 Сгенерировать JWT ключи
См. инструкцию: [backend/light_task/src/auth/README.md](./backend/light_task/src/auth/README.md).

### 4.4 Запустить backend + db + redis
```bash
docker compose -f docker-compose.dev.yml up --build
```

Backend:
- API: `http://localhost:8000/api/*`
- Health: `http://localhost:8000/api/health`
- Docs: `http://localhost:8000/docs`

### 4.5 Запустить frontend
```bash
cd frontend/light-task-frontend
pnpm install
cp .env.template .env
pnpm dev
```

Frontend: `http://localhost:5173`

## 5. Переменные окружения (.env)
### 5.1 Development
Используй `.env.template` как базу.

Обязательные переменные для backend runtime:
- `LIGHTTASK_CONFIG__DB__USER`
- `LIGHTTASK_CONFIG__DB__PASSWORD`
- `LIGHTTASK_CONFIG__DB__NAME`

По умолчанию в development аватары сохраняются локально:
- `LIGHTTASK_CONFIG__S3__BACKEND=local`
- файлы лежат в `backend/light_task/.local/avatar-storage`
- публичные URL отдаются backend'ом через `/local-storage/*`

Если нужно проверить реальный S3-compatible storage локально:
- `LIGHTTASK_CONFIG__S3__BACKEND=s3`
- `LIGHTTASK_CONFIG__S3__ACCESS_KEY`
- `LIGHTTASK_CONFIG__S3__SECRET_KEY`
- `LIGHTTASK_CONFIG__S3__BUCKET_NAME`

Важно для localhost cookie-flow:
- `LIGHTTASK_CONFIG__AUTH_JWT__SECURE=False`

Yandex OAuth / Yandex ID:
- `LIGHTTASK_CONFIG__YANDEX__CLIENT_ID`
- `LIGHTTASK_CONFIG__YANDEX__CLIENT_SECRET`
- `LIGHTTASK_CONFIG__YANDEX__REDIRECT_URI`
- `LIGHTTASK_CONFIG__FRONTEND__BASE_URL`

Для production callback: `https://kantano.ru/api/auth/yandex/callback`.
Backend завершает OAuth flow сам, ставит текущую `refresh_token` cookie и возвращает frontend на `/auth/yandex/callback`; access token через URL не передаётся.

Важно для realtime:
- `LIGHTTASK_CONFIG__REALTIME__REDIS_URL` (в compose dev/prod уже настроен на сервис `redis`)

### 5.2 Production (manual deploy без GitHub Actions)
Используй `.env.prod.template`.

Обязательные:
- `LIGHTTASK_CONFIG__DB__PASSWORD`
- `LIGHTTASK_CONFIG__S3__ACCESS_KEY`
- `LIGHTTASK_CONFIG__S3__SECRET_KEY`
- `LIGHTTASK_CONFIG__S3__BUCKET_NAME`
- `LIGHTTASK_CONFIG__YANDEX__CLIENT_ID`
- `LIGHTTASK_CONFIG__YANDEX__CLIENT_SECRET`
- `LIGHTTASK_CONFIG__YANDEX__REDIRECT_URI`
- `LIGHTTASK_CONFIG__FRONTEND__BASE_URL`
- `IMAGE_REPO_OWNER`
- `IMAGE_TAG`
- `SWAGGER_HASH`

Важно:
- часть параметров backend в проде зафиксирована прямо в `docker-compose.prod.yml` (`DB host/user/name`, `RUN host/port`, `CORS`, `INVITE base URL`)
- если деплой через GitHub Actions, секреты задаются в `Repository Settings -> Secrets and variables -> Actions`

## 6. JWT ключи (`certs`)
Нужны файлы:
- `jwt-private.pem`
- `jwt-public.pem`

Куда класть:
- Dev: `backend/light_task/certs/`
- Prod (`docker-compose.prod.yml`): `./certs/` рядом с compose-файлом

Подробности: [backend/light_task/src/auth/README.md](./backend/light_task/src/auth/README.md)

## 7. Caddy / Swagger пароль
`/docs`, `/openapi.json`, `/redoc` защищены Basic Auth через `SWAGGER_HASH`.

Сгенерировать новый bcrypt hash:
```bash
docker run --rm caddy caddy hash-password --plaintext "new_password"
```

Дальше:
- обнови `SWAGGER_HASH` в GitHub Secret (если деплой через Actions)
- или в серверном `.env` (если manual deploy)

Логин сейчас задаётся в [Caddyfile](./Caddyfile) строкой `Ilm1n {$SWAGGER_HASH}`.

## 8. Деплой (Production)
### 8.1 Через GitHub Actions (рекомендуется)
Workflow: [deploy.yml](./.github/workflows/deploy.yml)

Требуемые secrets:
- `DB_PASSWORD`
- `S3_ACCESS_KEY`
- `S3_SECRET_KEY`
- `S3_BUCKET_NAME`
- `JWT_PRIVATE_KEY`
- `JWT_PUBLIC_KEY`
- `SWAGGER_HASH`
- `VPS_HOST`
- `VPS_USER`
- `VPS_KEY`
- `YANDEX_CLIENT_ID`
- `YANDEX_CLIENT_SECRET`
- `YANDEX_REDIRECT_URI`
- `FRONTEND_BASE_URL`

Подробная памятка: [.github/workflows/README.md](./.github/workflows/README.md)

### 8.2 Ручной деплой (manual)
1. Подготовь `.env` из `.env.prod.template`.
2. Создай `./certs/` и положи туда JWT ключи.
3. Авторизуйся в GHCR:
```bash
docker login ghcr.io
```
4. Запусти деплой:
```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d --force-recreate --remove-orphans --wait
```

## 9. Полезные команды
### Экспорт актуальной OpenAPI схемы во frontend
```bash
cd backend/light_task
uv run python scripts/export_openapi.py
```

### Перегенерация frontend API client
```bash
cd backend/light_task
uv run python scripts/export_openapi.py

cd frontend/light-task-frontend
pnpm gen:api
```

### Проверка backend API (Schemathesis)
```bash
st run http://127.0.0.1:8000/openapi.json --checks all --max-examples 50
```

### Миграции (backend)
```bash
cd backend/light_task
uv run alembic upgrade head
```

### Backend realtime integration tests
```bash
docker compose -f docker-compose.test.yml up -d

cd backend/light_task
LIGHTTASK_TEST_DB_HOST=127.0.0.1 \
LIGHTTASK_TEST_DB_PORT=55432 \
LIGHTTASK_TEST_DB_USER=postgres \
LIGHTTASK_TEST_DB_PASSWORD=postgres \
LIGHTTASK_TEST_DB_NAME=lighttask_test \
LIGHTTASK_TEST_REDIS_URL=redis://127.0.0.1:56379/15 \
uv run pytest -q tests/test_realtime_integration.py

docker compose -f docker-compose.test.yml down -v
```

Важно:
- для integration tests использовать отдельные test PostgreSQL/Redis (не dev базы);
- тесты в `conftest.py` имеют safety-check и по умолчанию откажутся работать с non-test DB и Redis DB 0.

## 10. Документация проекта
- [AGENT_CONTEXT.md](./AGENT_CONTEXT.md) - короткий entrypoint для агентов
- [docs/project-audit/README.md](./docs/project-audit/README.md) - карта полного аудита
- [backend/light_task/README.md](./backend/light_task/README.md) - backend onboarding
- [frontend/light-task-frontend/README.md](./frontend/light-task-frontend/README.md) - frontend onboarding

## 11. Troubleshooting
- `401` на localhost после логина: проверь `LIGHTTASK_CONFIG__AUTH_JWT__SECURE=False` в `.env`.
- Backend не стартует и ругается на ключи: проверь `jwt-private.pem`/`jwt-public.pem` и путь `certs`.
- Upload аватаров падает при `LIGHTTASK_CONFIG__S3__BACKEND=s3`: проверь S3 credentials, bucket name и доступы.
- Swagger не открывается: проверь актуальность `SWAGGER_HASH` и перезапусти gateway.
