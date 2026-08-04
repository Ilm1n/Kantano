# Деплой и эксплуатация

В production все сервисы запускаются на одном Docker Compose host. Caddy завершает TLS, раздаёт Vue SPA
и проксирует `/api`, `/ws` и документацию FastAPI в backend. PostgreSQL и Redis доступны
только во внутренних Docker networks; аватары хранятся в S3-compatible bucket.

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

Нужные repository secrets:

- `DB_PASSWORD`;
- `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_NAME`;
- `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`;
- `YANDEX_CLIENT_ID`, `YANDEX_CLIENT_SECRET`, `YANDEX_REDIRECT_URI`;
- `FRONTEND_BASE_URL`;
- `SWAGGER_HASH`;
- `VPS_HOST`, `VPS_USER`, `VPS_KEY`.

`GITHUB_TOKEN` предоставляется Actions автоматически. Значения секретов не должны
храниться в репозитории или попадать в логи.

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

Backend entrypoint ждёт PostgreSQL и выполняет `alembic upgrade head` до запуска API.
Успешность деплоя контролируется endpoint'ом `/api/health`.

## Образы и откат

`IMAGE_REPO_OWNER` задаёт владельца GHCR packages, а `IMAGE_TAG` - версию обоих образов.
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
