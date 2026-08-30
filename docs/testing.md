# Тестирование

## Набор проверок

| Область | Инструменты | Что проверяется |
|---|---|---|
| Качество backend | Ruff, Basedpyright | Стиль, форматирование и типы в `src` |
| Backend unit | pytest, pytest-asyncio | Use cases, permissions, ordering и UnitOfWork без инфраструктуры |
| Backend integration | pytest, FastAPI TestClient | REST-сценарии, PostgreSQL, Redis, RabbitMQ, OAuth и realtime |
| Architecture | pytest | Запрет legacy services, commit вне UnitOfWork и прямой realtime publish |
| Frontend unit | Vitest, Vue Test Utils, jsdom | Auth, Yandex flow, board store и analytics context |
| Frontend build | vue-tsc, Vite | Типы и production-сборка |

## Backend

Полный набор требует отдельные PostgreSQL, Redis и RabbitMQ:

```bash
docker compose -f docker-compose.test.yml up -d

cd backend/light_task
uv sync --group dev
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv run pytest -q
```

После прогона из корня репозитория:

```bash
docker compose -f docker-compose.test.yml down
```

Тестовый Compose использует PostgreSQL на `55432`, Redis на `56379` с индексом `/15`
и RabbitMQ на `55672`. `tests/conftest.py` применяет миграции, очищает состояние между
тестами и отказывается запускать integration tests против БД без `test` в имени или
Redis DB 0. Вызовы внешнего email API выполняются через `httpx.MockTransport`; реальный
API-ключ не требуется. Тестовые JWT-ключи находятся в `tests/fixtures`.

Unit tests не требуют Docker:

```bash
cd backend/light_task
uv run pytest -q tests/unit
```

Отдельные запуски:

```bash
uv run pytest -q tests/test_architecture_guards.py
uv run pytest -q tests/test_auth_yandex.py
uv run pytest -q tests/test_realtime_integration.py
```

## Frontend

```bash
cd frontend/light-task-frontend
pnpm install
pnpm test:unit
pnpm build
```

Для разработки тестов в watch-режиме:

```bash
pnpm test:unit:watch
```

`pnpm build` сначала запускает `vue-tsc -b`, затем собирает приложение через Vite.

## Pre-commit и CI

Pre-commit настраивается из `backend/light_task`:

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

Workflow `.github/workflows/backend-tests.yml` запускается при backend-изменениях в
push/pull request в `main` и вручную. Он поднимает PostgreSQL, Redis и RabbitMQ как service
containers, затем выполняет Ruff, Basedpyright, миграции и полный pytest-набор.

Frontend-проверки сейчас не входят в GitHub Actions, поэтому `pnpm test:unit` и
`pnpm build` выполняются локально перед merge frontend-изменений.
