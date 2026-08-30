#!/bin/bash
set -e

DB_HOST="${LIGHTTASK_CONFIG__DB__HOST:-db}"
DB_PORT="${LIGHTTASK_CONFIG__DB__PORT:-5432}"

echo "Waiting for postgres at ${DB_HOST}:${DB_PORT}..."

while ! nc -z "$DB_HOST" "$DB_PORT"; do
  sleep 0.5
done

echo "PostgreSQL started at ${DB_HOST}:${DB_PORT}"

if [ "${LIGHTTASK_SKIP_MIGRATIONS:-0}" != "1" ]; then
  echo "Running migrations..."
  alembic upgrade head
fi

echo "Starting application..."
exec "$@"
