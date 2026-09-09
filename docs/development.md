# Локальная разработка

Все Task-команды выполняются из корня репозитория. Полный список: `task --list`.
Подробности о задаче: `task --summary <task>`.

## Требования

- Task v3;
- Docker с Compose;
- Node.js 24 и pnpm 9 или 10;
- Python 3.12 и [uv](https://docs.astral.sh/uv/);
- OpenSSL для генерации JWT-ключей.

## Первый запуск

Подготовьте локальную конфигурацию, JWT-ключи, зависимости и pre-commit hooks:

```bash
task setup
```

Запустите dev-окружение и frontend:

```bash
task dev
```

Docker-сервисы можно поднять отдельно в фоне, а frontend запустить в другом терминале:

```bash
task dev:up
task dev:frontend
```

После `Ctrl+C` Vite остановится, а Docker-сервисы продолжат работу. Для просмотра логов
и остановки используйте `task dev:logs` и `task dev:down`.

| Сервис | Адрес |
|---|---|
| Frontend | `http://localhost:5173` |
| API | `http://localhost:8000/api` |
| Swagger UI | `http://localhost:8000/docs` |
| Liveness | `http://localhost:8000/api/health` |
| Readiness (PostgreSQL) | `http://localhost:8000/api/health/ready` |
| Mailpit inbox | `http://localhost:8025` |
| PostgreSQL | `localhost:5432` |
| Redis | `localhost:6379` |

RabbitMQ доступен только сервисам внутри Compose network. `docker-compose.dev.yml`
также запускает Celery worker и outbox publisher. Init-сервисы копируют JWT-ключи в
закрытый volume и подготавливают локальное хранилище, а отдельный сервис `migrations`
применяет Alembic migrations до запуска приложения и фоновых процессов.

## Конфигурация

Backend читает переменные с префиксом `LIGHTTASK_CONFIG__`; вложенность задаётся через
двойное подчёркивание. Все настройки с безопасными примерами находятся в корневом
`.env.template`.

Минимально обязательны:

```dotenv
LIGHTTASK_CONFIG__DB__USER=lighttask_user
LIGHTTASK_CONFIG__DB__PASSWORD=change_me_db_password
LIGHTTASK_CONFIG__DB__NAME=lighttask
LIGHTTASK_CONFIG__AUTH_JWT__SECURE=False
```

`SECURE=False` нужен только для refresh-cookie на localhost по HTTP. В production
используется безопасное значение по умолчанию `True`.

По умолчанию dev-окружение отправляет письма регистрации в локальный Mailpit:

```dotenv
LIGHTTASK_CONFIG__EMAIL__PROVIDER=mailpit
LIGHTTASK_CONFIG__MAILPIT__HOST=localhost
LIGHTTASK_CONFIG__MAILPIT__SMTP_PORT=1025
LIGHTTASK_CONFIG__MAILPIT__TIMEOUT_SECONDS=5
LIGHTTASK_CONFIG__MAILPIT__FROM_EMAIL=no-reply@kantano.local
LIGHTTASK_CONFIG__MAILPIT__FROM_NAME=Kantano
```

Inbox доступен на `http://localhost:8025`. Внутри Compose Celery worker подключается
к SMTP по адресу `mailpit:1025`; при локальном запуске worker используется
`localhost:1025`. TLS и аутентификация в локальном режиме не нужны.

Для переключения на реальную отправку через Resend используйте:

```dotenv
LIGHTTASK_CONFIG__EMAIL__PROVIDER=resend
LIGHTTASK_CONFIG__RESEND__API_KEY=<real-key>
LIGHTTASK_CONFIG__RESEND__BASE_URL=https://api.resend.com
LIGHTTASK_CONFIG__RESEND__FROM_EMAIL=no-reply@kantano.ru
LIGHTTASK_CONFIG__RESEND__FROM_NAME=Kantano
```

Домен отправителя должен быть подтверждён в Resend. Ключ хранится только в локальном
`.env` или GitHub Secrets и не должен попадать в commit или логи. Без ключа backend
запустится, но Celery не сможет отправить письмо подтверждения.

После изменения `LIGHTTASK_CONFIG__EMAIL__PROVIDER` пересоздайте worker, чтобы он
перечитал `.env`:

```bash
docker compose -f docker-compose.dev.yml up -d --force-recreate celery-worker
```

Mailpit разрешён только вне production. Production-конфигурация с провайдером `mailpit`
не пройдёт валидацию при запуске.

По умолчанию аватары сохраняются локально. Чтобы проверить S3-compatible storage,
установите `LIGHTTASK_CONFIG__S3__BACKEND=s3` и заполните access key, secret key и
bucket name.

Yandex OAuth локально необязателен. Без `CLIENT_ID` и `CLIENT_SECRET` обычные
регистрация и login продолжают работать; кнопка Yandex покажет ошибку конфигурации.

Frontend использует только `VITE_API_URL`. Пустое значение включает same-origin режим:
Vite проксирует `/api` и `/ws` на `127.0.0.1:8000`. Для отдельного backend host задайте
адрес backend без завершающего `/` и без суффикса `/api`, например
`VITE_API_URL=http://localhost:8000`.

## Запуск backend вне Docker

PostgreSQL, Redis и фоновые сервисы можно оставить в Compose:

```bash
docker compose -f docker-compose.dev.yml up -d db redis rabbitmq celery-worker outbox-publisher

cd backend/light_task
uv sync --group dev
uv run alembic upgrade head
uv run uvicorn src.main:main_app --host 127.0.0.1 --port 8000 --reload
```

Значения `DB__HOST=localhost` и `REALTIME__REDIS_URL=redis://localhost:6379/0` из
корневого `.env` подходят для такого режима. События регистрации обработают worker и
publisher, работающие внутри Compose.

## Миграции

Команды выполняются из `backend/light_task`:

```bash
# применить миграции
task db:migrate

# создать миграцию из изменений SQLAlchemy models
task db:revision MESSAGE="describe change"

# откатить одну ревизию
cd backend/light_task
uv run alembic downgrade -1
```

Сгенерированную миграцию нужно проверить вручную. В production схема меняется только
через миграции.

## OpenAPI и frontend-клиент

После изменений в router или Pydantic schema обновляются файл `openapi.json` и
TypeScript-клиент:

```bash
task api:generate
```

После генерации в commit добавляются `openapi.json` и изменения в `src/api/client`.

## JWT-ключи

Имена файлов фиксированы: `jwt-private.pem` и `jwt-public.pem`. Проверить пару можно так:

```bash
openssl rsa -in backend/light_task/certs/jwt-private.pem -check -noout
openssl rsa \
  -in backend/light_task/certs/jwt-private.pem \
  -pubout -outform PEM \
  | diff - backend/light_task/certs/jwt-public.pem
```

Приватный ключ не должен попадать в Git. При ротации заменяйте оба файла: ранее
выданные JWT после этого станут недействительными. Чтобы Compose перечитал новую пару:

```bash
docker compose -f docker-compose.dev.yml up -d --force-recreate jwt-certs-init backend
```

## Частые проблемы

- `401` сразу после login: проверьте `LIGHTTASK_CONFIG__AUTH_JWT__SECURE=False`.
- Backend не стартует: проверьте наличие обоих JWT-файлов и логи `jwt-certs-init`.
- Realtime не подключается: frontend должен открываться через Vite на порту 5173, а
  Redis - отвечать на `localhost:6379`.
- Письмо не приходит: для Mailpit проверьте inbox на `localhost:8025` и логи
  `outbox-publisher`, `celery-worker`, `rabbitmq`, `mailpit`; для Resend дополнительно
  проверьте API key и статус домена отправителя.
- Аватар не загружается: для local backend проверьте `S3__BACKEND=local`; для S3 -
  credentials, bucket и endpoint.
- После изменения API появились TypeScript-ошибки: повторно экспортируйте OpenAPI и
  выполните `pnpm gen:api`.
