# Kantano Backend

FastAPI-приложение с REST API и WebSocket realtime для Kantano.

## Структура

```text
src/
├── auth/          # login, refresh и Yandex OAuth
├── registration/  # подтверждение email, outbox и Celery-задачи
├── users/         # профиль, пароль и аватары
├── projects/      # проекты, участники и роли
├── boards/        # колонки, задачи и ordering
├── tags/          # теги проекта
├── invitations/   # ссылки-приглашения
├── realtimev1/    # WebSocket, Redis Pub/Sub и presence
├── db/            # SQLAlchemy и UnitOfWork
└── shared/        # domain events и общие ошибки
```

Изменение данных проходит по цепочке `router → schema/DTO → use case →
permissions/repository → UnitOfWork → domain events`. Только `UnitOfWork` завершает
транзакцию; realtime публикуется после commit.

Подробнее: [архитектура](../../docs/architecture.md).

## Разработка

Основной development-режим запускается из корня репозитория:

```bash
docker compose -f docker-compose.dev.yml up --build
```

Для запуска backend непосредственно на хосте:

```bash
cd backend/light_task
uv sync --group dev
uv run alembic upgrade head
uv run uvicorn src.main:main_app --host 127.0.0.1 --port 8000 --reload
```

Backend использует Python 3.12. Конфигурация загружается из корневого `.env` и
переменных `LIGHTTASK_CONFIG__*`. PostgreSQL, Redis, RabbitMQ и JWT-ключи обязательны
для полного запуска. Для реальных писем регистрации нужен API key настроенного
почтового провайдера; Yandex OAuth и S3 в development можно не настраивать.

Полная настройка окружения: [локальная разработка](../../docs/development.md).

## Проверки

```bash
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv run pytest -q tests/unit
```

Полный pytest-набор использует отдельные PostgreSQL, Redis и RabbitMQ из
`../../docker-compose.test.yml`. Команды и правила изоляции описаны в
[руководстве по тестированию](../../docs/testing.md).

## API и миграции

При запущенном backend доступны Swagger UI на `http://localhost:8000/docs` и OpenAPI на
`http://localhost:8000/openapi.json`.

Frontend-контракт нужно обновлять после изменений API:

```bash
uv run python scripts/export_openapi.py
cd ../../frontend/light-task-frontend
pnpm gen:api
```

Миграции находятся в `alembic/versions` и применяются командой
`uv run alembic upgrade head`. В Docker Compose их выполняет отдельный одноразовый
сервис `migrations` до запуска backend, Celery worker и outbox publisher.
