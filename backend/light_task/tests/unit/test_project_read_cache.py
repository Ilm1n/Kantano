from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from redis.exceptions import ConnectionError

from src.boards.dto import GetProjectBoardQuery
from src.boards.events import BoardsDomainEventDispatcher, ColumnDeleted
from src.boards.schemas import ColumnRead
from src.boards.use_cases import GetProjectBoardUseCase
from src.cache.redis import RedisCache
from src.config import CacheConfig
from src.invitations.events import InvitationAccepted, InvitationsDomainEventDispatcher
from src.projects.cache import ProjectReadCache
from src.projects.constants import ProjectRole
from src.projects.dto import ListProjectMembersQuery
from src.projects.events import MemberRemoved, ProjectDeleted, ProjectsDomainEventDispatcher
from src.projects.schemas import ProjectMemberRead
from src.projects.use_cases import ListProjectMembersUseCase
from src.tags.dto import ListProjectTagsQuery
from src.tags.events import TagDeleted, TagsDomainEventDispatcher
from src.tags.schemas import TagRead
from src.tags.use_cases import ListProjectTagsUseCase
from src.users.schemas import UserCollaborator

pytestmark = pytest.mark.no_infra


class FakeRedisClient:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.set_calls: list[tuple[str, bytes, int]] = []
        self.deleted: list[str] = []
        self.closed = False
        self.get_error = False
        self.set_error = False
        self.delete_error = False

    async def get(self, key: str) -> bytes | None:
        if self.get_error:
            raise ConnectionError("cache unavailable")
        return self.values.get(key)

    async def set(self, key: str, value: bytes, *, ex: int) -> None:
        if self.set_error:
            raise ConnectionError("cache unavailable")
        self.values[key] = value
        self.set_calls.append((key, value, ex))

    async def delete(self, *keys: str) -> None:
        if self.delete_error:
            raise ConnectionError("cache unavailable")
        for key in keys:
            self.values.pop(key, None)
            self.deleted.append(key)

    async def aclose(self) -> None:
        self.closed = True


class FakeSession:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        return False


class FakeProjectReadCache:
    def __init__(self, *, board=None, members=None, tags=None) -> None:
        self.board = board
        self.members = members
        self.tags = tags
        self.reads: list[tuple[str, int]] = []
        self.invalidations: list[tuple[str, int]] = []

    async def get_board(self, project_id: int):
        self.reads.append(("board", project_id))
        return self.board

    async def set_board(self, project_id: int, value) -> None:
        self.board = value

    async def get_members(self, project_id: int):
        self.reads.append(("members", project_id))
        return self.members

    async def set_members(self, project_id: int, value) -> None:
        self.members = value

    async def get_tags(self, project_id: int):
        self.reads.append(("tags", project_id))
        return self.tags

    async def set_tags(self, project_id: int, value) -> None:
        self.tags = value

    async def invalidate_board(self, project_id: int) -> None:
        self.invalidations.append(("board", project_id))

    async def invalidate_members(self, project_id: int) -> None:
        self.invalidations.append(("members", project_id))

    async def invalidate_tags(self, project_id: int) -> None:
        self.invalidations.append(("tags", project_id))

    async def invalidate_project(self, project_id: int) -> None:
        self.invalidations.append(("project", project_id))


def _cache_config(**overrides) -> CacheConfig:
    return CacheConfig(
        enabled=overrides.get("enabled", True),
        redis_url="redis://cache.invalid/0",
        ttl_seconds=overrides.get("ttl_seconds", 60),
        max_value_bytes=overrides.get("max_value_bytes", 512 * 1024),
        socket_timeout_seconds=0.2,
    )


@pytest.mark.asyncio
async def test_project_read_cache_round_trip_ttl_invalidation_and_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeRedisClient()
    span_calls: list[tuple[str, dict[str, str]]] = []
    attribute_calls: list[tuple[str, str]] = []

    class RecordingTracer:
        def start_as_current_span(self, name: str, *, attributes: dict[str, str]):
            span_calls.append((name, attributes))
            return nullcontext()

    monkeypatch.setattr("src.cache.redis.redis.from_url", lambda *args, **kwargs: client)
    monkeypatch.setattr("src.projects.cache.tracer", RecordingTracer())
    monkeypatch.setattr(
        "src.projects.cache.set_current_span_attribute",
        lambda name, value: attribute_calls.append((name, value)),
    )
    config = _cache_config(ttl_seconds=45)
    backend = RedisCache(config)
    cache = ProjectReadCache(backend, config)
    board = [
        ColumnRead(
            id=1,
            project_id=10,
            name="Todo",
            position=65536,
            tasks_limit=None,
            tasks=[],
        )
    ]

    await backend.start()
    assert await cache.get_board(10) is None
    await cache.set_board(10, board)

    assert await cache.get_board(10) == board
    assert client.set_calls[0][0] == "cache:v1:project:10:board"
    assert client.set_calls[0][2] == 45
    assert span_calls == [
        ("cache.get", {"cache.name": "project_board", "cache.operation": "get"}),
        ("cache.get", {"cache.name": "project_board", "cache.operation": "get"}),
    ]
    assert attribute_calls == [
        ("cache.result", "miss"),
        ("cache.result", "hit"),
    ]

    await cache.invalidate_board(10)
    assert await cache.get_board(10) is None
    assert client.deleted == ["cache:v1:project:10:board"]

    await backend.aclose()
    assert client.closed is True


@pytest.mark.asyncio
async def test_project_read_cache_treats_invalid_and_oversized_values_as_misses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeRedisClient()
    monkeypatch.setattr("src.cache.redis.redis.from_url", lambda *args, **kwargs: client)
    config = _cache_config(max_value_bytes=5)
    backend = RedisCache(config)
    cache = ProjectReadCache(backend, config)
    await backend.start()
    key = "cache:v1:project:5:tags"
    client.values[key] = b"not-json"

    assert await cache.get_tags(5) is None
    assert client.deleted == [key]

    await cache.set_tags(5, [TagRead(id=1, project_id=5, name="Backend", color="#9CA3AF")])
    assert client.set_calls == []


@pytest.mark.asyncio
async def test_redis_cache_is_disabled_or_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    from_url_calls = 0

    def from_url(*args, **kwargs):
        nonlocal from_url_calls
        from_url_calls += 1
        return FakeRedisClient()

    monkeypatch.setattr("src.cache.redis.redis.from_url", from_url)
    disabled = RedisCache(_cache_config(enabled=False))
    await disabled.start()
    assert (await disabled.get("key", cache_name="project_board")).status == "disabled"
    assert from_url_calls == 0

    failing_client = FakeRedisClient()
    failing_client.get_error = True
    monkeypatch.setattr("src.cache.redis.redis.from_url", lambda *args, **kwargs: failing_client)
    enabled = RedisCache(_cache_config())
    await enabled.start()
    result = await enabled.get("key", cache_name="project_board")
    assert result.status == "error"
    assert result.value is None

    failing_client.set_error = True
    failing_client.delete_error = True
    await enabled.set(
        "key",
        b"value",
        ttl_seconds=60,
        cache_name="project_board",
    )
    await enabled.delete("key", "other-key", cache_name="project_board")


@pytest.mark.asyncio
async def test_read_use_cases_authorize_before_returning_cached_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    board = [
        ColumnRead(
            id=1,
            project_id=10,
            name="Todo",
            position=1,
            tasks_limit=None,
            tasks=[],
        )
    ]
    members = [
        ProjectMemberRead(
            id=2,
            user=UserCollaborator(
                id=3,
                username="member",
                full_name=None,
                avatar_url=None,
                email="member@example.com",
            ),
            role=ProjectRole.MEMBER,
            joined_at=datetime(2026, 9, 8, tzinfo=UTC),
        )
    ]
    tags = [TagRead(id=4, project_id=10, name="Backend", color="#9CA3AF")]
    cache = FakeProjectReadCache(board=board, members=members, tags=tags)
    calls: list[str] = []

    class BoardRepository:
        def __init__(self, session: object) -> None:
            pass

        async def get_project_member(self, *, project_id: int, user_id: int):
            calls.append("board_member")
            return SimpleNamespace(role=ProjectRole.MEMBER)

        async def list_project_columns(self, project_id: int):
            raise AssertionError("board query must not run on cache hit")

    class ProjectRepository:
        def __init__(self, session: object) -> None:
            pass

        async def get_member(self, *, project_id: int, user_id: int):
            calls.append("members_member")
            return SimpleNamespace(role=ProjectRole.MEMBER)

        async def list_project_members(self, project_id: int):
            raise AssertionError("members query must not run on cache hit")

    class TagRepository:
        def __init__(self, session: object) -> None:
            pass

        async def get_project_member(self, *, project_id: int, user_id: int):
            calls.append("tags_member")
            return SimpleNamespace(role=ProjectRole.MEMBER)

        async def list_project_tags(self, project_id: int):
            raise AssertionError("tags query must not run on cache hit")

    monkeypatch.setattr("src.boards.use_cases.BoardRepository", BoardRepository)
    monkeypatch.setattr("src.projects.use_cases.ProjectRepository", ProjectRepository)
    monkeypatch.setattr("src.tags.use_cases.TagRepository", TagRepository)

    def session_factory() -> FakeSession:
        return FakeSession()

    board_result = await GetProjectBoardUseCase(
        session_factory,  # type: ignore[arg-type]
        cache=cache,  # type: ignore[arg-type]
    ).execute(GetProjectBoardQuery(project_id=10, actor_user_id=1))
    members_result = await ListProjectMembersUseCase(
        session_factory,  # type: ignore[arg-type]
        cache=cache,  # type: ignore[arg-type]
    ).execute(ListProjectMembersQuery(project_id=10, actor_user_id=1))
    tags_result = await ListProjectTagsUseCase(
        session_factory,  # type: ignore[arg-type]
        cache=cache,  # type: ignore[arg-type]
    ).execute(ListProjectTagsQuery(project_id=10, actor_user_id=1))

    assert board_result == board
    assert members_result == members
    assert tags_result == tags
    assert calls == ["board_member", "members_member", "tags_member"]


@pytest.mark.asyncio
async def test_domain_dispatchers_invalidate_exact_project_read_caches() -> None:
    cache = FakeProjectReadCache()
    publisher = SimpleNamespace()

    def session_factory() -> FakeSession:
        return FakeSession()

    await BoardsDomainEventDispatcher(
        session_factory,  # type: ignore[arg-type]
        publisher,  # type: ignore[arg-type]
        cache,  # type: ignore[arg-type]
    ).dispatch([ColumnDeleted(column_id=1, project_id=10)])
    await TagsDomainEventDispatcher(
        session_factory,  # type: ignore[arg-type]
        publisher,  # type: ignore[arg-type]
        cache,  # type: ignore[arg-type]
    ).dispatch([TagDeleted(tag_id=1, project_id=11)])
    await ProjectsDomainEventDispatcher(
        session_factory,  # type: ignore[arg-type]
        publisher,  # type: ignore[arg-type]
        cache,  # type: ignore[arg-type]
    ).dispatch(
        [
            MemberRemoved(user_id=2, project_id=12),
            ProjectDeleted(project_id=13),
        ]
    )
    await InvitationsDomainEventDispatcher(
        session_factory,  # type: ignore[arg-type]
        publisher,  # type: ignore[arg-type]
        cache,  # type: ignore[arg-type]
    ).dispatch(
        [
            InvitationAccepted(
                user_id=3,
                role=ProjectRole.MEMBER,
                project_id=14,
            )
        ]
    )

    assert cache.invalidations == [
        ("board", 10),
        ("board", 11),
        ("tags", 11),
        ("members", 12),
        ("project", 13),
        ("members", 14),
    ]
