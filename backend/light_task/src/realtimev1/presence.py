from __future__ import annotations

import asyncio
import contextlib
from collections import defaultdict
from dataclasses import dataclass

import redis.asyncio as redis

from src.logger import get_logger

logger = get_logger("src.realtimev1.presence")


@dataclass
class PresenceSnapshotItem:
    task_id: int
    viewing_user_ids: list[int]
    editing_user_ids: list[int]


class PresenceService:
    def __init__(
        self,
        *,
        redis_url: str,
        key_prefix: str,
        ttl_seconds: int,
    ):
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds
        self._redis: redis.Redis | None = None
        self._available = False
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def is_available(self) -> bool:
        return self._available

    async def start(self) -> None:
        if self._redis:
            return
        await self._ensure_client(operation="start")

    async def stop(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None
        self._available = False
        self._loop = None

    async def mark(self, *, project_id: int, task_id: int, user_id: int, mode: str) -> None:
        client = await self._ensure_client(operation="mark")
        if not client:
            return
        key = self._presence_key(
            project_id=project_id,
            task_id=task_id,
            mode=mode,
            user_id=user_id,
        )
        try:
            await client.set(key, "1", ex=self._ttl_seconds)
        except Exception as exc:
            await self._mark_unavailable(operation="mark", exc=exc)

    async def unmark(
        self,
        *,
        project_id: int,
        task_id: int,
        user_id: int,
        mode: str,
    ) -> None:
        client = await self._ensure_client(operation="unmark")
        if not client:
            return
        key = self._presence_key(
            project_id=project_id,
            task_id=task_id,
            mode=mode,
            user_id=user_id,
        )
        try:
            await client.delete(key)
        except Exception as exc:
            await self._mark_unavailable(operation="unmark", exc=exc)

    async def heartbeat(
        self,
        *,
        project_id: int,
        task_id: int,
        user_id: int,
        mode: str,
    ) -> None:
        client = await self._ensure_client(operation="heartbeat")
        if not client:
            return
        key = self._presence_key(
            project_id=project_id,
            task_id=task_id,
            mode=mode,
            user_id=user_id,
        )
        try:
            await client.expire(key, self._ttl_seconds)
        except Exception as exc:
            await self._mark_unavailable(operation="heartbeat", exc=exc)

    async def snapshot(self, *, project_id: int) -> list[PresenceSnapshotItem]:
        client = await self._ensure_client(operation="snapshot")
        if not client:
            return []
        match_pattern = f"{self._key_prefix}:{project_id}:*"
        grouped: dict[int, dict[str, set[int]]] = defaultdict(
            lambda: {"viewing": set(), "editing": set()}
        )

        try:
            async for key in client.scan_iter(match=match_pattern):
                parsed = self._parse_key(key)
                if not parsed:
                    continue
                task_id, mode, user_id = parsed
                grouped[task_id][mode].add(user_id)
        except Exception as exc:
            await self._mark_unavailable(operation="snapshot", exc=exc)
            return []

        items: list[PresenceSnapshotItem] = []
        for task_id in sorted(grouped.keys()):
            item = grouped[task_id]
            items.append(
                PresenceSnapshotItem(
                    task_id=task_id,
                    viewing_user_ids=sorted(item["viewing"]),
                    editing_user_ids=sorted(item["editing"]),
                )
            )
        return items

    async def _ensure_client(self, *, operation: str) -> redis.Redis | None:
        current_loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not current_loop:
            await self._mark_unavailable(
                operation=f"{operation}_loop_switch",
                exc=RuntimeError("presence redis client loop switched"),
            )

        if not self._redis:
            self._redis = redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            self._loop = current_loop

        if not self._available:
            try:
                await self._redis.ping()
            except Exception as exc:
                await self._mark_unavailable(operation=operation, exc=exc)
                return None
            self._available = True
            self._loop = current_loop

        return self._redis

    def _presence_key(
        self,
        *,
        project_id: int,
        task_id: int,
        mode: str,
        user_id: int,
    ) -> str:
        return f"{self._key_prefix}:{project_id}:{task_id}:{mode}:{user_id}"

    def _parse_key(self, key: str) -> tuple[int, str, int] | None:
        parts = key.split(":")
        if len(parts) < 7:
            return None

        try:
            task_id = int(parts[-3])
            mode = parts[-2]
            user_id = int(parts[-1])
        except ValueError:
            return None

        if mode not in {"viewing", "editing"}:
            return None
        return task_id, mode, user_id

    async def _mark_unavailable(self, *, operation: str, exc: Exception) -> None:
        logger.warning(
            "Presence redis unavailable during operation=%s; realtime presence temporarily disabled",
            operation,
            exc_info=exc,
        )
        self._available = False
        if self._redis:
            with contextlib.suppress(Exception):
                await self._redis.aclose()
            self._redis = None
