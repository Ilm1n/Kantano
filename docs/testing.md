# Тестирование

Все Task-команды выполняются из корня репозитория. Полный список: `task --list`.
Подробности о задаче: `task --summary <task>`.

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

Полный backend-набор вместе с отдельными PostgreSQL, Redis и RabbitMQ запускается так:

```bash
task test:backend
```

Task автоматически останавливает тестовый Compose после успешного прогона или ошибки.
Локальные dev-контейнеры и именованные volumes не затрагиваются.

Тестовый Compose использует PostgreSQL на `55432`, Redis на `16379` с индексом `/15`
и RabbitMQ на `55672`. `tests/conftest.py` применяет миграции, очищает состояние между
тестами и отказывается запускать integration tests против БД без `test` в имени или
Redis DB 0. Вызовы внешнего email API выполняются через `httpx.MockTransport`; реальный
API-ключ не требуется. Тестовые JWT-ключи находятся в `tests/fixtures`.

Unit tests не требуют Docker:

```bash
task test:backend:unit
```

Отдельные запуски:

```bash
uv run pytest -q tests/test_architecture_guards.py
uv run pytest -q tests/test_auth_yandex.py
uv run pytest -q tests/test_realtime_integration.py
```

## Frontend

```bash
task test:frontend
```

Для разработки тестов в watch-режиме:

```bash
pnpm test:unit:watch
```

`pnpm build` сначала запускает `vue-tsc -b`, затем собирает приложение через Vite.

Все backend/frontend тесты последовательно запускаются командой `task test`, а полный
локальный quality gate, включая Ruff, Basedpyright, Compose validation и frontend build,
— командой `task check`.

## Pre-commit и CI

Pre-commit устанавливается командой `task setup`. Ручной полный прогон:

```bash
uv run --project backend/light_task pre-commit run --all-files
```

Workflow `.github/workflows/backend-tests.yml` запускается при backend-изменениях в
push/pull request в `main` и вручную. Он поднимает PostgreSQL, Redis и RabbitMQ как service
containers, затем выполняет Ruff, Basedpyright, миграции и полный pytest-набор.

Frontend-проверки сейчас не входят в GitHub Actions, поэтому `pnpm test:unit` и
`pnpm build` выполняются локально перед merge frontend-изменений.
