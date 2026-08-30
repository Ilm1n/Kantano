# Деплой и эксплуатация

В production все сервисы запускаются на одном Docker Compose host. Caddy завершает TLS,
раздаёт Vue SPA и проксирует `/api`, `/ws` и документацию FastAPI в backend. PostgreSQL,
Redis и RabbitMQ доступны только во внутренних Docker networks; Celery отправляет
транзакционные письма через внешний email API, а аватары хранятся в S3-compatible bucket.

## GitHub Actions

Основной сценарий - ручной запуск workflow `.github/workflows/deploy.yml` через
`workflow_dispatch`.

При запуске workflow:

1. собирает backend и frontend images;
2. публикует теги `main` и short commit SHA в GHCR;
3. формирует `.env.prod` и JWT-файлы из GitHub Secrets;
4. копирует Compose, Caddyfile, env и сертификаты на VPS;
5. выполняет `docker compose pull` и ждёт успешного health check;
6. оставляет в GHCR пять последних версий каждого image.

Repository Secrets:

- `DB_PASSWORD`;
- `S3_ACCESS_KEY`, `S3_SECRET_KEY`;
- `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`;
- `YANDEX_CLIENT_SECRET`;
- `RESEND_API_KEY`;
- `RABBITMQ_PASSWORD`;
- `SWAGGER_HASH`;
- `VPS_HOST`, `VPS_USER`, `VPS_KEY`.

Repository Variables:

- `S3_BUCKET_NAME`;
- `FRONTEND_BASE_URL`;
- `YANDEX_CLIENT_ID`, `YANDEX_REDIRECT_URI`;
- `RESEND_FROM_EMAIL=no-reply@kantano.ru`;
- `RESEND_FROM_NAME=Kantano`.

`GITHUB_TOKEN` предоставляется Actions автоматически. Значения секретов не должны
храниться в репозитории или попадать в логи.

Для отправки писем домен из `RESEND_FROM_EMAIL` должен быть подтверждён в Resend.
Kantano использует HTTP API Resend, поэтому открытые исходящие SMTP-порты на VPS
не требуются.

## Ручной запуск Compose

На сервере подготовьте `.env` из шаблона и JWT-пару:

```bash
cp .env.prod.template .env
mkdir -p certs
```

Заполните `.env`, положите в `certs/` файлы `jwt-private.pem` и `jwt-public.pem`, затем:

```bash
chmod 600 certs/jwt-private.pem
docker login ghcr.io
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d --force-recreate --remove-orphans --wait
```

Одноразовый сервис `migrations` ждёт PostgreSQL и выполняет `alembic upgrade head` до
запуска API, Celery worker и outbox publisher.
Успешность деплоя контролируется endpoint'ом `/api/health`.

RabbitMQ использует отдельный vhost `kantano`, durable quorum-очередь
`email_verification` и publisher confirms. Это устраняет зависимость Celery от
устаревшего global QoS в RabbitMQ 4. Переход на classic queue требует отдельной
проверки совместимости.

Миграция заполняет `email_verified_at` всем существующим пользователям, поэтому после
обновления они продолжают входить без повторного подтверждения почты.

## Контроль состояния

Состояние production-окружения и последние записи основных сервисов доступны через:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=100 migrations backend rabbitmq celery-worker outbox-publisher
```

Успешный запуск означает завершение `migrations` с кодом `0` и рабочее состояние
`backend`, `rabbitmq`, `celery-worker` и `outbox-publisher` без циклических перезапусков.

При проверочной регистрации в логах отражаются четыре события: создана заявка,
опубликовано outbox-событие, Celery получил задачу, почтовый провайдер принял письмо.
После обработки очередь остаётся пустой, подтверждение создаёт пользователя, а обычный
вход возвращает токены.

## Образы и откат

Владелец GHCR packages определяется автоматически из `github.repository_owner`, а `IMAGE_TAG` задаёт
версию обоих образов.
Для ручного отката укажите ранее опубликованный short SHA и повторно выполните `pull` и
`up --wait`. Автоматическая очистка registry сохраняет только пять последних версий,
поэтому старые теги не гарантированы.

## Caddy и Swagger

Caddy автоматически получает TLS-сертификаты для `kantano.ru` и перенаправляет
альтернативные домены на основной. `/docs`, `/openapi.json` и `/redoc` защищены Basic
Auth.

Чтобы сменить пароль, сгенерируйте новый bcrypt hash:

```bash
docker run --rm caddy caddy hash-password --plaintext "new_password"
```

Обновите `SWAGGER_HASH` в GitHub Secrets либо server `.env` и пересоздайте gateway.
Имя пользователя Basic Auth задаётся в `Caddyfile`.

## Ротация JWT

Пара JWT-ключей передаётся на сервер из GitHub Secrets или каталога `./certs`.
Production Compose копирует их в закрытый Docker volume с правами `600`/`644`.

При ротации замените оба секрета или оба файла и пересоздайте `jwt-certs-init` и backend.
Все выданные ранее access/refresh tokens станут недействительными, пользователям
потребуется войти повторно.
