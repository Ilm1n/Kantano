# Документация Kantano

В корневом [README](../README.md) собраны обзор проекта и короткий сценарий запуска.
В этой папке находятся подробные руководства для разработки и эксплуатации.

| Документ | О чём |
|---|---|
| [Архитектура](./architecture.md) | Компоненты, backend-слои, LangGraph-агент, фоновые задачи, realtime и API-контракт |
| [Локальная разработка](./development.md) | Окружение, LM Studio и облачные модели, запуск сервисов, миграции и генерация API-клиента |
| [Тестирование](./testing.md) | Backend/frontend проверки, сценарии помощника, тестовая инфраструктура и CI |
| [Деплой](./deployment.md) | Production Compose, GitHub Actions, секреты и проверка после запуска |
| [Observability](./observability.md) | Архитектура telemetry pipeline, логи, трассы, метрики, dashboards, alerts и диагностика |

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
- observability stack - `observability/` и `docker-compose.observability.yml`;
- схема данных - SQLAlchemy models и Alembic migrations; внутренние таблицы LangGraph - PostgreSQL checkpointer.
