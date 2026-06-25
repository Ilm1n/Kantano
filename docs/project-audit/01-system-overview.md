# 01. System Overview

## Purpose
Дать единый architectural map проекта `Kantano`, чтобы быстро понять границы системы, ключевые потоки, ответственность подсистем и места с повышенным риском изменений.

## Current Behavior
### 1) System Shape
Проект имеет monorepo-структуру из двух основных runtime-компонентов:
- `backend/light_task` — FastAPI + SQLAlchemy (async) + Alembic + JWT auth + S3 avatar storage.
- `frontend/light-task-frontend` — Vue 3 + Vite + Pinia + PrimeVue + generated OpenAPI client.

Deployment shape в production:
- `gateway` (Caddy) обслуживает SPA и reverse-proxy для API.
- `backend` (FastAPI/uvicorn).
- `db` (PostgreSQL 15).

### 2) Bounded Contexts (Backend)
Функциональные контексты разделены на модули:
- `auth` — login/refresh/logout, токены и cookies.
- `users` — регистрация, профиль, avatar upload/delete.
- `projects` — проекты, роли, участники.
- `boards` — колонки и задачи (kanban).
- `tags` — project tags и связи task-tag.
- `invitations` — invite links и принятие приглашений.

### 3) Bounded Contexts (Frontend)
UI-модули отражают backend-домены:
- `modules/auth`
- `modules/projects`
- `modules/board`
- `modules/invitations`
- `modules/profile`
- `modules/landing`

Store topology:
- `auth.store` — session/token lifecycle.
- `projects.store` — listing/create project.
- `board.store` — orchestration для board/tasks/members/tags/invitations.

### 4) Canonical Runtime Flows (Text Diagrams)
#### Auth flow
`LoginPage -> auth.store.login -> POST /api/auth/login -> access token in memory + refresh token cookie -> guarded routes`

`401 on API -> axios response interceptor -> POST /api/auth/refresh (cookie) -> new access token -> replay original request`

#### Board flow
`BoardPage -> board.store.fetchBoard(projectId) -> parallel requests (project + columns + members + tags) -> render draggable board`

`Drag task -> board.store.moveTask -> PATCH /api/tasks/{task_id}/move -> backend recalculates position`

#### Invite flow
`Invite dialog -> POST /api/projects/{id}/invite -> link/QR`

`/invite/{token} -> accept page -> if unauthenticated save pending token -> register/login -> POST /api/invitations/{token}/accept -> redirect to project board`

### 5) Data & Contract Surface
- OpenAPI содержит `25` path entries (включая `/api/health`).
- Backend сериализация использует camelCase aliasing на schema-уровне.
- Frontend API client сгенерирован из `openapi.json` (`openapi-typescript-codegen`).

### 6) High-Level Architecture Notes
- Backend использует service-layer pattern: routers thin, business logic in `service.py`.
- Permission checks централизованы в `dependencies.py` по доменам (project/task/tag).
- Project recency (`updated_at`) обновляется через `touch_project` во множестве сценариев мутаций.
- Caddy защищает Swagger/OpenAPI базовой авторизацией.

## Dependencies
### Core Runtime Dependencies
- Backend: `fastapi`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pyjwt[crypto]`, `pwdlib[argon2]`, `aioboto3`.
- Frontend: `vue`, `vue-router`, `pinia`, `axios`, `primevue`, `tailwindcss`, `vee-validate`, `zod`, `openapi-typescript-codegen`.
- Infra: `postgres:15`, `caddy`, Docker/Compose.

### External Services
- S3-compatible storage endpoint for avatars.
- Yandex Metrika (conditionally enabled by consent + host rules).

## Risks
- System-level риск несинхронности ожиданий: landing page и proxy routes декларируют WebSocket сценарии, но backend WebSocket endpoints отсутствуют.
- Сложность board-сценариев: позиционирование задач через float-gap + rebalance повышает вероятность edge-cases при конкурентных перемещениях.
- Security/permissions риск: права приглашений и ролевые переходы требуют отдельного контроля (детально в `07-risk-register.md`).

## Open Questions
- Нужен ли реальный real-time layer (WebSockets/SSE), или текущая модель intended как request/response only?
- Нужно ли отделять public profile и internal collaborator profile (email visibility policy)?
- Является ли допуск `OWNER` роли в инвайтах бизнес-требованием или дефектом авторизации?

## References
- `backend/light_task/src/main.py:40`
- `backend/light_task/src/main.py:55`
- `backend/light_task/src/main.py:81`
- `backend/light_task/src/config.py:78`
- `backend/light_task/src/config.py:83`
- `backend/light_task/src/config.py:86`
- `backend/light_task/src/config.py:90`
- `backend/light_task/src/auth/router.py:11`
- `backend/light_task/src/users/router.py:17`
- `backend/light_task/src/projects/router.py:23`
- `backend/light_task/src/boards/router.py:28`
- `backend/light_task/src/tags/router.py:11`
- `backend/light_task/src/invitations/router.py:15`
- `frontend/light-task-frontend/src/router/index.ts:18`
- `frontend/light-task-frontend/src/router/index.ts:77`
- `frontend/light-task-frontend/src/modules/auth/store/auth.store.ts:28`
- `frontend/light-task-frontend/src/modules/board/store/board.store.ts:113`
- `frontend/light-task-frontend/src/modules/board/store/board.store.ts:276`
- `frontend/light-task-frontend/src/modules/invitations/pages/AcceptInvitationPage.vue:31`
- `frontend/light-task-frontend/src/modules/invitations/pages/AcceptInvitationPage.vue:42`
- `frontend/light-task-frontend/openapi.json:8`
- `frontend/light-task-frontend/openapi.json:1765`
- `backend/light_task/src/schemas.py:10`
- `Caddyfile:17`
- `Caddyfile:21`
- `docker-compose.prod.yml:4`
- `docker-compose.prod.yml:56`
- `docker-compose.prod.yml:29`
