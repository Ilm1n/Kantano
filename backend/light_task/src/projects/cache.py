from __future__ import annotations

from typing import TypeVar

import orjson
from fastapi import Request
from pydantic import TypeAdapter, ValidationError

from src.boards.schemas import ColumnRead
from src.cache.redis import RedisCache
from src.config import CacheConfig
from src.observability.metrics import record_cache_operation
from src.observability.tracing import set_current_span_attribute
from src.projects.schemas import ProjectMemberRead
from src.tags.schemas import TagRead

T = TypeVar("T")

PROJECT_BOARD_CACHE = "project_board"
PROJECT_MEMBERS_CACHE = "project_members"
PROJECT_TAGS_CACHE = "project_tags"

_BOARD_ADAPTER = TypeAdapter(list[ColumnRead])
_MEMBERS_ADAPTER = TypeAdapter(list[ProjectMemberRead])
_TAGS_ADAPTER = TypeAdapter(list[TagRead])


class ProjectReadCache:
    def __init__(self, backend: RedisCache, config: CacheConfig) -> None:
        self._backend = backend
        self._ttl_seconds = config.ttl_seconds

    async def get_board(self, project_id: int) -> list[ColumnRead] | None:
        return await self._get(
            key=self._key(project_id, "board"),
            cache_name=PROJECT_BOARD_CACHE,
            adapter=_BOARD_ADAPTER,
        )

    async def set_board(self, project_id: int, value: list[ColumnRead]) -> None:
        await self._set(
            key=self._key(project_id, "board"),
            cache_name=PROJECT_BOARD_CACHE,
            value=value,
            adapter=_BOARD_ADAPTER,
        )

    async def invalidate_board(self, project_id: int) -> None:
        await self._backend.delete(
            self._key(project_id, "board"),
            cache_name=PROJECT_BOARD_CACHE,
        )

    async def get_members(self, project_id: int) -> list[ProjectMemberRead] | None:
        return await self._get(
            key=self._key(project_id, "members"),
            cache_name=PROJECT_MEMBERS_CACHE,
            adapter=_MEMBERS_ADAPTER,
        )

    async def set_members(self, project_id: int, value: list[ProjectMemberRead]) -> None:
        await self._set(
            key=self._key(project_id, "members"),
            cache_name=PROJECT_MEMBERS_CACHE,
            value=value,
            adapter=_MEMBERS_ADAPTER,
        )

    async def invalidate_members(self, project_id: int) -> None:
        await self._backend.delete(
            self._key(project_id, "members"),
            cache_name=PROJECT_MEMBERS_CACHE,
        )

    async def get_tags(self, project_id: int) -> list[TagRead] | None:
        return await self._get(
            key=self._key(project_id, "tags"),
            cache_name=PROJECT_TAGS_CACHE,
            adapter=_TAGS_ADAPTER,
        )

    async def set_tags(self, project_id: int, value: list[TagRead]) -> None:
        await self._set(
            key=self._key(project_id, "tags"),
            cache_name=PROJECT_TAGS_CACHE,
            value=value,
            adapter=_TAGS_ADAPTER,
        )

    async def invalidate_tags(self, project_id: int) -> None:
        await self._backend.delete(
            self._key(project_id, "tags"),
            cache_name=PROJECT_TAGS_CACHE,
        )

    async def invalidate_project(self, project_id: int) -> None:
        await self.invalidate_board(project_id)
        await self.invalidate_members(project_id)
        await self.invalidate_tags(project_id)

    async def _get(
        self,
        *,
        key: str,
        cache_name: str,
        adapter: TypeAdapter[T],
    ) -> T | None:
        cached = await self._backend.get(key, cache_name=cache_name)
        if cached.status != "hit" or cached.value is None:
            if cached.status == "miss":
                record_cache_operation(cache_name, "get", "miss")
                set_current_span_attribute("cache.result", "miss")
            return None

        try:
            value = adapter.validate_json(cached.value)
        except (ValidationError, ValueError, orjson.JSONDecodeError):
            record_cache_operation(cache_name, "get", "invalid")
            set_current_span_attribute("cache.result", "invalid")
            await self._backend.delete(key, cache_name=cache_name)
            return None

        record_cache_operation(cache_name, "get", "hit")
        set_current_span_attribute("cache.result", "hit")
        return value

    async def _set(
        self,
        *,
        key: str,
        cache_name: str,
        value: T,
        adapter: TypeAdapter[T],
    ) -> None:
        payload = orjson.dumps(adapter.dump_python(value, mode="json", by_alias=True))
        await self._backend.set(
            key,
            payload,
            ttl_seconds=self._ttl_seconds,
            cache_name=cache_name,
        )

    @staticmethod
    def _key(project_id: int, entry: str) -> str:
        return f"cache:v1:project:{project_id}:{entry}"


def get_project_read_cache(request: Request) -> ProjectReadCache:
    cache = getattr(request.app.state, "project_read_cache", None)
    if not isinstance(cache, ProjectReadCache):
        raise RuntimeError("Project read cache is not initialized")
    return cache
