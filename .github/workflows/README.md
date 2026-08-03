# CI/CD Notes (`.github/workflows`)

В репозитории используется workflow [deploy.yml](./deploy.yml) для production deploy.

## Trigger
Сейчас запуск вручную: `workflow_dispatch`.

## Required GitHub Secrets
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

## Что делает workflow
1. Собирает backend/frontend Docker images и публикует в GHCR.
2. Формирует `.env.prod` и `certs/*.pem` из secrets.
3. Копирует `docker-compose.prod.yml`, `Caddyfile`, `.env.prod`, `certs/` на VPS.
4. На VPS выполняет `docker compose pull` + `up -d --force-recreate --remove-orphans --wait`; production Compose сам подготавливает закрытый volume для JWT-ключей перед запуском backend.
5. Удаляет старые версии контейнерных образов в registry.

## Как поменять пароль Swagger (Caddy basic auth)
1. Сгенерируй bcrypt hash:
```bash
docker run --rm caddy caddy hash-password --plaintext "new_password"
```
2. Обнови `SWAGGER_HASH` в GitHub Secrets.
3. Запусти `deploy.yml`.

## Если нужен manual deploy
- используй корневой `.env.prod.template`
- JWT ключи положи в `./certs/` рядом с `docker-compose.prod.yml`
