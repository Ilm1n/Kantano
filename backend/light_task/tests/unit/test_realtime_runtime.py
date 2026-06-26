from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from src.projects.constants import ProjectRole
from src.realtimev1.connection_manager import ConnectionManager
from src.realtimev1.events import (
    RealtimeDeliveryMessage,
    RealtimeEventType,
    RealtimeScope,
    new_event_envelope,
)
from src.realtimev1.presence import PresenceService
from src.realtimev1.runtime import RealtimeRuntime


class FakeEventBus:
    async def start(
        self,
        consumer: Callable[[RealtimeDeliveryMessage], Awaitable[None]],
    ) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def publish(self, message: RealtimeDeliveryMessage) -> None:
        return None


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.close_calls: list[dict[str, Any]] = []

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)

    async def close(self, *, code: int, reason: str) -> None:
        self.close_calls.append({"code": code, "reason": reason})


@pytest.mark.asyncio
async def test_member_removed_publishes_project_presence_changed_after_forced_disconnect() -> None:
    connections = ConnectionManager()
    runtime = RealtimeRuntime(
        event_bus=FakeEventBus(),
        connection_manager=connections,
        presence_service=PresenceService(
            redis_url="redis://localhost:6379/0",
            key_prefix="test:presence",
            ttl_seconds=30,
        ),
        presence_sync_interval_seconds=60,
    )
    owner_ws = FakeWebSocket()
    member_ws = FakeWebSocket()
    project_id = 100

    await connections.register_project(
        user_id=1,
        project_id=project_id,
        role=ProjectRole.OWNER,
        websocket=owner_ws,  # type: ignore[arg-type]
    )
    await connections.register_project(
        user_id=2,
        project_id=project_id,
        role=ProjectRole.MEMBER,
        websocket=member_ws,  # type: ignore[arg-type]
    )

    await runtime.consume(
        RealtimeDeliveryMessage(
            envelope=new_event_envelope(
                event_type=RealtimeEventType.MEMBER_REMOVED,
                scope=RealtimeScope.PROJECT,
                actor_user_id=1,
                project_id=project_id,
                payload={"userId": 2},
            ),
            project_id=project_id,
        )
    )

    presence_events = [
        message
        for message in owner_ws.sent
        if message.get("eventType") == RealtimeEventType.PROJECT_PRESENCE_CHANGED
    ]
    assert presence_events
    assert presence_events[-1]["payload"]["activeUserCount"] == 1
    assert member_ws.close_calls == [{"code": 1008, "reason": "project_access_revoked"}]
