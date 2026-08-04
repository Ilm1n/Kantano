# Kantano Frontend

Клиентская часть Kantano - SPA на Vue 3 и TypeScript. Приложение взаимодействует с
backend API и получает realtime-обновления через WebSocket.

## Структура

```text
src/
├── api/           # сгенерированный OpenAPI client и Axios configuration
├── modules/       # auth, projects, board, invitations, profile, realtime
├── layouts/       # authenticated application shell
├── shared/        # UI, consent и analytics
├── composables/   # общие Vue composables
└── router/        # маршруты и auth guards
```

Состояние приложения хранится в Pinia stores. REST-запросы идут через сгенерированный
TypeScript-клиент, а realtime-события приходят через user/project
WebSocket-каналы.

Подробнее: [архитектура](../../docs/architecture.md).

## Запуск

Понадобятся Node.js 24 и pnpm 9.

```bash
pnpm install
cp .env.template .env
pnpm dev
```

Frontend откроется на `http://localhost:5173`. При пустом `VITE_API_URL` Vite
проксирует `/api` и `/ws` в backend на `http://127.0.0.1:8000`.

## Команды

```bash
pnpm dev              # development server
pnpm test:unit        # Vitest
pnpm test:unit:watch  # Vitest в watch-режиме
pnpm build            # vue-tsc + production build
pnpm preview          # preview каталога dist
pnpm gen:api          # генерация клиента из openapi.json
```

Подробности: [локальная разработка](../../docs/development.md) и
[тестирование](../../docs/testing.md).

## API-клиент

После изменений backend-контракта сначала экспортируйте OpenAPI:

```bash
cd ../../backend/light_task
uv run python scripts/export_openapi.py

cd ../../frontend/light-task-frontend
pnpm gen:api
```

Каталог `src/api/client` генерируется из `openapi.json`, поэтому ручные изменения в нём
будут перезаписаны при следующей генерации.

## Analytics debug

Yandex Metrika в production включается только на разрешённых host'ах и после согласия
пользователя. Для localhost можно включить диагностику через
`http://localhost:5173/?analytics_debug=1`, а выключить и очистить флаг - через
`?analytics_debug=0`.
