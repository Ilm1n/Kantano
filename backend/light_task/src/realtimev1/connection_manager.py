from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from src.logger import get_logger
from src.projects.constants import ProjectRole
from src.realtimev1.events import RealtimeAudience, RealtimeDeliveryMessage

logger = get_logger("src.realtimev1.connections")


@dataclass
class PresenceState:
    task_id: int
    mode: str


@dataclass
class ConnectionContext:
    user_id: int
    project_id: int | None
    role: ProjectRole | None = None
    presence_states: set[tuple[int, str]] = field(default_factory=set)


class ConnectionManager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._user_connections: dict[int, set[WebSocket]] = {}
        self._project_connections: dict[int, dict[int, set[WebSocket]]] = {}
        self._contexts: dict[WebSocket, ConnectionContext] = {}

    async def register_user(self, *, user_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            self._user_connections.setdefault(user_id, set()).add(websocket)
            self._contexts[websocket] = ConnectionContext(user_id=user_id, project_id=None)

    async def register_project(
        self,
        *,
        user_id: int,
        project_id: int,
        role: ProjectRole,
        websocket: WebSocket,
    ) -> None:
        async with self._lock:
            self._project_connections.setdefault(project_id, {}).setdefault(user_id, set()).add(
                websocket
            )
            self._contexts[websocket] = ConnectionContext(
                user_id=user_id,
                project_id=project_id,
                role=role,
            )

    async def unregister(self, websocket: WebSocket) -> ConnectionContext | None:
        async with self._lock:
            context = self._contexts.pop(websocket, None)
            if not context:
                return None

            user_set = self._user_connections.get(context.user_id)
            if user_set:
                user_set.discard(websocket)
                if not user_set:
                    self._user_connections.pop(context.user_id, None)

            if context.project_id is not None:
                project_map = self._project_connections.get(context.project_id)
                if project_map:
                    project_user_set = project_map.get(context.user_id)
                    if project_user_set:
                        project_user_set.discard(websocket)
                        if not project_user_set:
                            project_map.pop(context.user_id, None)
                    if not project_map:
                        self._project_connections.pop(context.project_id, None)

            return context

    async def mark_presence(
        self,
        websocket: WebSocket,
        *,
        task_id: int,
        mode: str,
    ) -> None:
        async with self._lock:
            context = self._contexts.get(websocket)
            if not context:
                return
            context.presence_states.add((task_id, mode))

    async def unmark_presence(
        self,
        websocket: WebSocket,
        *,
        task_id: int,
        mode: str,
    ) -> None:
        async with self._lock:
            context = self._contexts.get(websocket)
            if not context:
                return
            context.presence_states.discard((task_id, mode))

    async def get_context(self, websocket: WebSocket) -> ConnectionContext | None:
        async with self._lock:
            return self._contexts.get(websocket)

    async def active_project_ids(self) -> list[int]:
        async with self._lock:
            return [project_id for project_id, users in self._project_connections.items() if users]

    async def active_project_user_count(self, *, project_id: int) -> int:
        async with self._lock:
            return len(self._project_connections.get(project_id, {}))

    async def update_role(self, *, project_id: int, user_id: int, role: ProjectRole) -> None:
        async with self._lock:
            project_map = self._project_connections.get(project_id, {})
            for ws in project_map.get(user_id, set()):
                context = self._contexts.get(ws)
                if context:
                    context.role = role

    async def close_project_user_connections(
        self,
        *,
        project_id: int,
        user_id: int,
        code: int = 1008,
        reason: str = "project_access_revoked",
    ) -> None:
        connections: list[WebSocket] = []
        async with self._lock:
            project_map = self._project_connections.get(project_id, {})
            connections = list(project_map.get(user_id, set()))

        await self._close_connections(connections, code=code, reason=reason)

    async def close_project_connections(
        self,
        *,
        project_id: int,
        code: int = 1001,
        reason: str = "project_closed",
    ) -> None:
        connections: list[WebSocket] = []
        async with self._lock:
            project_map = self._project_connections.get(project_id, {})
            for user_connections in project_map.values():
                connections.extend(user_connections)

        await self._close_connections(connections, code=code, reason=reason)

    async def dispatch(self, message: RealtimeDeliveryMessage) -> None:
        payload = message.envelope.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
        if message.user_ids:
            await self._send_user_targets(
                user_ids=message.user_ids,
                payload=payload,
            )

        if message.project_id is not None:
            await self._send_project_targets(
                project_id=message.project_id,
                payload=payload,
                audience=message.audience,
                exclude_user_ids=set(message.exclude_user_ids),
            )

    async def _send_user_targets(
        self,
        *,
        user_ids: list[int],
        payload: dict[str, Any],
    ) -> None:
        targets: list[WebSocket] = []
        async with self._lock:
            for user_id in user_ids:
                targets.extend(list(self._user_connections.get(user_id, set())))

        await self._send_payload_to_connections(targets, payload)

    async def _send_project_targets(
        self,
        *,
        project_id: int,
        payload: dict[str, Any],
        audience: RealtimeAudience,
        exclude_user_ids: set[int],
    ) -> None:
        targets: list[WebSocket] = []
        async with self._lock:
            project_map = self._project_connections.get(project_id, {})
            for user_id, user_connections in project_map.items():
                if user_id in exclude_user_ids:
                    continue
                for ws in user_connections:
                    if audience == RealtimeAudience.MANAGER:
                        context = self._contexts.get(ws)
                        if not context or context.role not in (
                            ProjectRole.OWNER,
                            ProjectRole.MANAGER,
                        ):
                            continue
                    targets.append(ws)

        await self._send_payload_to_connections(targets, payload)

    async def _send_payload_to_connections(
        self,
        connections: list[WebSocket],
        payload: dict[str, Any],
    ) -> None:
        stale_connections: list[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_json(payload)
            except Exception:
                stale_connections.append(ws)

        for ws in stale_connections:
            await self.unregister(ws)

    async def _close_connections(
        self,
        connections: list[WebSocket],
        *,
        code: int,
        reason: str,
    ) -> None:
        for ws in connections:
            with contextlib.suppress(Exception):
                await ws.close(code=code, reason=reason)
            await self.unregister(ws)
