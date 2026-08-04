# Архитектура Kantano

Kantano состоит из Vue SPA, FastAPI backend, PostgreSQL и Redis. В production Caddy
раздаёт собранный frontend, завершает TLS и проксирует HTTP/WebSocket-трафик в backend.

```mermaid
flowchart TD
    client["Browser / Vue SPA"]
    gateway["Caddy gateway"]
    api["FastAPI application"]
    postgres[("PostgreSQL")]
    redis[("Redis Pub/Sub + presence")]
    files["Local or S3-compatible storage"]
    oauth["Yandex ID"]

    client -->|"HTML, CSS, JS"| gateway
    client -->|"REST /api/*"| gateway
    client -->|"WebSocket /ws/*"| gateway
    gateway --> api
    api --> postgres
    api --> redis
    api --> files
    api --> oauth
```

## Backend-модули

Backend разделён на несколько функциональных модулей:

- `auth` - login, refresh/logout и Yandex OAuth;
- `users` - регистрация, профиль, пароль и аватар;
- `projects` - проекты, участники и роли;
- `boards` - колонки, задачи, порядок и перемещение карточек;
- `tags` - теги проекта;
- `invitations` - создание, просмотр, отзыв и принятие приглашений;
- `realtimev1` - WebSocket-подключения, Redis event bus и presence.

Во frontend эти области находятся в `src/modules`. Состояние приложения хранится в
Pinia stores, а Vue-компоненты отвечают за отображение и пользовательский ввод.

## Backend-слои и транзакции

Изменение данных проходит следующий путь:

```mermaid
flowchart LR
    router["Router"] --> schemas["Pydantic schemas"]
    schemas --> dto["DTO / command"]
    dto --> usecase["Use case"]
    usecase --> policy["Permissions"]
    usecase --> repo["Repository"]
    repo --> uow["UnitOfWork"]
    uow -->|"commit"| db[("PostgreSQL")]
    uow -->|"after commit"| events["Domain event dispatcher"]
    events --> realtime["Realtime publisher"]
```

- Routers знают о FastAPI, cookies и HTTP-ответах, но не содержат бизнес-логику.
- Use cases реализуют пользовательские сценарии и выбрасывают `AppError`, а не
  `HTTPException`.
- Repositories инкапсулируют SQLAlchemy и не вызывают `commit()`/`rollback()`.
- Permissions проверяют доступ на основе ролей `OWNER`, `MANAGER`, `MEMBER`.
- `UnitOfWork` владеет транзакцией и отправляет накопленные domain events только после
  успешного commit.
- Read-сценарии также проходят через query use cases и repositories, но не открывают
  `UnitOfWork`, если не изменяют данные.

Архитектурные тесты проверяют соблюдение этих правил.

## Авторизация

Локальный login возвращает короткоживущий access token и устанавливает refresh token в
`HttpOnly` cookie. Frontend держит access token только в памяти. После перезагрузки
страницы `restoreSession()` вызывает `/api/auth/refresh`, получает новый access token и
загружает профиль пользователя.

Yandex ID - дополнительный identity provider. OAuth callback обрабатывает backend:
проверяет state, получает профиль, находит или создаёт локального пользователя, ставит
ту же refresh-cookie и возвращает SPA на `/auth/yandex/callback`. Локальный access token
не передаётся в URL.

## Realtime

Backend предоставляет два авторизованных WebSocket-канала:

- `/ws/user` - изменения списка проектов и членства пользователя;
- `/ws/projects/{project_id}` - доска, настройки, участники, приглашения и presence.

Клиент первым сообщением передаёт access token. Для project scope backend дополнительно
проверяет членство и роль. Каждое событие имеет версионированный envelope с `eventId`,
`eventType`, actor, payload и необязательным `clientMutationId`.

Изменения записываются через REST. UI сразу применяет optimistic update, отправляет
mutation и сверяет результат с итоговым событием от сервера. После reconnect store
повторно запрашивает нужные данные. Redis Pub/Sub обеспечивает доставку между
несколькими backend-процессами; presence хранится с TTL и не блокирует редактирование.

## API-контракт и ошибки

Все REST-маршруты находятся под `/api`. Актуальная схема генерируется самим FastAPI и
доступна локально через `/openapi.json` и `/docs`. Frontend хранит экспортированную схему
в `frontend/light-task-frontend/openapi.json` и генерирует по ней TypeScript-клиент.

Известные ошибки преобразуются в единый JSON-ответ с машинным кодом и параметрами.
Необработанные исключения логируются и возвращаются как `UNKNOWN_ERROR` со статусом 500.

## Данные и файлы

PostgreSQL хранит пользователей, проекты, участников, колонки, задачи, теги и
приглашения. Порядок колонок и задач задаётся числовым `position`; операции перемещения
и rebalance находятся в backend.

Аватары в development сохраняются в Docker volume и отдаются FastAPI через
`/local-storage`. В production используется S3-compatible bucket. Схема БД развивается
только через Alembic migrations.
