# Документация Kantano

В корневом [README](../README.md) собраны обзор проекта и короткий сценарий запуска.
В этой папке находятся подробные руководства для разработки и эксплуатации.

| Документ | О чём |
|---|---|
| [Архитектура](./architecture.md) | Компоненты системы, backend-слои, авторизация, realtime и API-контракт |
| [Локальная разработка](./development.md) | Настройка окружения, запуск, миграции и генерация API-клиента |
| [Тестирование](./testing.md) | Backend/frontend проверки, тестовая инфраструктура и CI |
| [Деплой](./deployment.md) | Production Compose, GitHub Actions, секреты и ручной запуск |

README отдельных приложений описывают только контекст соответствующего пакета:

- [backend](../backend/light_task/README.md);
- [frontend](../frontend/light-task-frontend/README.md).

## Где искать актуальную информацию

- REST API - FastAPI routers/schemas и сгенерированный `openapi.json`;
- конфигурация - `src/config.py` и `.env*.template`;
- backend-зависимости и проверки - `pyproject.toml`;
- frontend-скрипты и зависимости - `package.json`;
- сервисы и сценарии запуска - `docker-compose.*.yml`;
- CI/CD - файлы в `.github/workflows/`;
- схема данных - SQLAlchemy models и цепочка Alembic migrations.
