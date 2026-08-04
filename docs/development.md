# Локальная разработка

## Требования

- Docker с Compose;
- Node.js 24 и pnpm 9;
- Python 3.12 и [uv](https://docs.astral.sh/uv/) - только для запуска backend вне Docker
  и локальных проверок;
- OpenSSL для генерации JWT-ключей.

## Первый запуск

Из корня репозитория создайте локальную конфигурацию и пару RSA-ключей:

```bash
cp .env.template .env

mkdir -p backend/light_task/certs
openssl genrsa -out backend/light_task/certs/jwt-private.pem 2048
openssl rsa \
  -in backend/light_task/certs/jwt-private.pem \
  -pubout \
  -out backend/light_task/certs/jwt-public.pem
```

Запустите backend-инфраструктуру:

```bash
docker compose -f docker-compose.dev.yml up --build
```

В отдельном терминале запустите frontend:

```bash
cd frontend/light-task-frontend
pnpm install
cp .env.template .env
pnpm dev
```

| Сервис | Адрес |
|---|---|
| Frontend | `http://localhost:5173` |
| API | `http://localhost:8000/api` |
| Swagger UI | `http://localhost:8000/docs` |
| Health check | `http://localhost:8000/api/health` |
| PostgreSQL | `localhost:5432` |
| Redis | `localhost:6379` |

`docker-compose.dev.yml` запускает PostgreSQL, Redis и backend. Init-сервисы копируют
JWT-ключи в закрытый volume и подготавливают volume локального хранилища. Backend при
старте ждёт PostgreSQL и автоматически применяет Alembic migrations.

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

PostgreSQL и Redis можно оставить в Compose:

```bash
docker compose -f docker-compose.dev.yml up -d db redis

cd backend/light_task
uv sync --group dev
uv run alembic upgrade head
uv run uvicorn src.main:main_app --host 127.0.0.1 --port 8000 --reload
```

Значения `DB__HOST=localhost` и `REALTIME__REDIS_URL=redis://localhost:6379/0` из
корневого `.env` подходят для такого режима.

## Миграции

Команды выполняются из `backend/light_task`:

```bash
# применить миграции
uv run alembic upgrade head

# создать миграцию из изменений SQLAlchemy models
uv run alembic revision --autogenerate -m "describe change"

# откатить одну ревизию
uv run alembic downgrade -1
```

Сгенерированную миграцию нужно проверить вручную. В production схема меняется только
через миграции.

## OpenAPI и frontend-клиент

После изменений в router или Pydantic schema обновляются файл `openapi.json` и
TypeScript-клиент:

```bash
cd backend/light_task
uv run python scripts/export_openapi.py

cd ../../frontend/light-task-frontend
pnpm gen:api
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
- Аватар не загружается: для local backend проверьте `S3__BACKEND=local`; для S3 -
  credentials, bucket и endpoint.
- После изменения API появились TypeScript-ошибки: повторно экспортируйте OpenAPI и
  выполните `pnpm gen:api`.
