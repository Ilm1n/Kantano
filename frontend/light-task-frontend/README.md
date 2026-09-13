# Kantano Frontend

Клиентская часть Kantano — приложение на Vue 3 и TypeScript и статически
генерируемый лендинг. Приложение взаимодействует с backend API и получает
realtime-обновления через WebSocket.

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

Публичный auth flow включает регистрацию, экран ожидания письма и страницу
подтверждения, где пользователь после перехода по одноразовой ссылке задаёт пароль.

Подробнее: [архитектура](../../docs/architecture.md).

## Запуск

Все Task-команды выполняются из корня репозитория. Полный список: `task --list`.
Подробности о задаче: `task --summary <task>`.

Понадобятся Node.js 24 и pnpm 9 или 10. Из корня репозитория:

```bash
task setup  # подготовить весь проект и установить зависимости
task dev    # поднять backend-инфраструктуру и запустить frontend
```

Frontend откроется на `http://localhost:5173`. При пустом `VITE_API_URL` Vite
проксирует `/api` и `/ws` в backend на `http://127.0.0.1:8000`.

## Низкоуровневые команды

Для изолированной работы с frontend из этого каталога:

```bash
pnpm dev              # development server без запуска backend
pnpm test:unit        # однократный прогон Vitest
pnpm test:unit:watch  # Vitest в watch-режиме
pnpm build            # vue-tsc + production build
pnpm preview          # preview каталога dist
pnpm gen:api          # генерация клиента из openapi.json
```

Подробности: [локальная разработка](../../docs/development.md) и
[тестирование](../../docs/testing.md).

## Публичная страница и сборка

`pnpm build` проверяет типы, собирает клиентские ресурсы и рендерит Vue-лендинг
через `vue/server-renderer` в `dist/index.html`. Затем проверяется контракт HTML:
контент, локальные ресурсы и метаданные. Промежуточный серверный bundle остаётся
в `node_modules/.tmp/landing-ssr` и не публикуется.

Caddy отдаёт `/` как готовый лендинг, а маршруты приложения — через `dist/app.html`
с `noindex`. Отсутствующие статические ресурсы возвращают 404. Переход между
лендингом и приложением загружает новый документ; тема и согласие на cookie
сохраняются в браузере. Лендинг не восстанавливает сессию и не зависит от API.

Для проверки результата выполните `pnpm build`, затем `pnpm preview` из этого
каталога. Preview использует то же разделение маршрутов; `pnpm dev` рендерит
лендинг в браузере для быстрой разработки. Проверку без JavaScript выполняют
на production-сборке. Docker запускает ту же сборку в Node builder stage;
готовые файлы обслуживает Caddy без серверного Vue/Node runtime.

`public/llms.txt` содержит краткую справку о продукте; обновлять её при изменении
возможностей и статуса. Контакт для сообщений об уязвимостях находится в
`public/.well-known/security.txt`.
`Expires` до 1 сентября 2027 года; новая дата должна быть менее чем через год.

## API-клиент

После изменений backend-контракта сначала экспортируйте OpenAPI:

```bash
task api:generate  # экспортировать OpenAPI и обновить TypeScript-клиент
```

Каталог `src/api/client` генерируется из `openapi.json`, поэтому ручные изменения в нём
будут перезаписаны при следующей генерации.

## Analytics debug

Yandex Metrika в production включается только на разрешённых host'ах и после согласия
пользователя. Для localhost можно включить диагностику через
`http://localhost:5173/?analytics_debug=1`, а выключить и очистить флаг - через
`?analytics_debug=0`.
