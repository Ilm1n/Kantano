from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import WebSocketDisconnect
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.projects.constants import ProjectRole
from src.realtimev1.auth import WsAuthContext
from src.realtimev1.connection_manager import ConnectionManager
from src.realtimev1.events import (
    RealtimeDeliveryMessage,
    RealtimeEventType,
    RealtimeScope,
    new_event_envelope,
)
from src.realtimev1.presence import PresenceService
from src.realtimev1.router import _traced_project_message_type, user_realtime_ws
from src.realtimev1.runtime import RealtimeRuntime
from src.realtimev1.serialization import deserialize_delivery_message, serialize_delivery_message

pytestmark = pytest.mark.no_infra


def test_only_meaningful_websocket_messages_create_operation_spans() -> None:
    assert _traced_project_message_type({"type": "task.presence.heartbeat"}) is None
    assert _traced_project_message_type({"type": "ping"}) is None
    assert (
        _traced_project_message_type({"type": RealtimeEventType.TASK_EDITING_STARTED})
        == RealtimeEventType.TASK_EDITING_STARTED
    )


@pytest.mark.asyncio
async def test_websocket_connect_span_ends_before_receive_loop(monkeypatch) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    test_tracer = provider.get_tracer(__name__)
    monkeypatch.setattr("src.realtimev1.router.tracer", test_tracer)

    active_span_ids: dict[str, int] = {}

    class Socket:
        async def accept(self) -> None:
            assert not trace.get_current_span().get_span_context().is_valid

        async def receive_json(self) -> dict[str, str]:
            assert not trace.get_current_span().get_span_context().is_valid
            raise WebSocketDisconnect()

    class Session:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_args: object) -> None:
            return None

    class Connections:
        async def register_user(self, **_kwargs: object) -> None:
            span_context = trace.get_current_span().get_span_context()
            assert span_context.is_valid
            active_span_ids["connect"] = span_context.span_id

        async def unregister(self, _websocket: object) -> None:
            assert not trace.get_current_span().get_span_context().is_valid

    async def authenticate(_websocket: object) -> WsAuthContext:
        return WsAuthContext(user_id=1, username=None, email=None, expires_at=None)

    async def is_active(_session: object, *, user_id: int) -> bool:
        return user_id == 1

    monkeypatch.setattr("src.realtimev1.router._authenticate_socket", authenticate)
    monkeypatch.setattr("src.realtimev1.router.ensure_user_is_active", is_active)
    monkeypatch.setattr(
        "src.realtimev1.router.db_helper.async_session_maker",
        lambda: Session(),
    )

    runtime = SimpleNamespace(connections=Connections())
    await user_realtime_ws(Socket(), runtime)  # type: ignore[arg-type]

    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == ["realtime.websocket.connect"]
    assert spans[0].context is not None
    assert active_span_ids == {"connect": spans[0].context.span_id}
    provider.shutdown()


class FakeEventBus:
    def __init__(self) -> None:
        self.published: list[RealtimeDeliveryMessage] = []

    async def start(
        self,
        consumer: Callable[[RealtimeDeliveryMessage], Awaitable[None]],
    ) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def publish(self, message: RealtimeDeliveryMessage) -> None:
        self.published.append(message)


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


@pytest.mark.asyncio
async def test_realtime_delivery_keeps_publisher_trace_across_serialization(monkeypatch) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    test_tracer = provider.get_tracer(__name__)
    monkeypatch.setattr("src.realtimev1.runtime.tracer", test_tracer)

    event_bus = FakeEventBus()
    runtime = RealtimeRuntime(
        event_bus=event_bus,
        connection_manager=ConnectionManager(),
        presence_service=PresenceService(
            redis_url="redis://localhost:6379/0",
            key_prefix="test:presence",
            ttl_seconds=30,
        ),
        presence_sync_interval_seconds=60,
    )
    message = RealtimeDeliveryMessage(
        envelope=new_event_envelope(
            event_type=RealtimeEventType.PROJECT_UPDATED,
            scope=RealtimeScope.PROJECT,
            actor_user_id=1,
            payload={"projectId": 1},
        )
    )

    with test_tracer.start_as_current_span("api.request") as parent:
        await runtime.publish(message)

    published = event_bus.published[0]
    assert published.trace_context is not None
    received = deserialize_delivery_message(serialize_delivery_message(published))
    await runtime.consume(received)

    spans = {span.name: span for span in exporter.get_finished_spans()}
    delivery = spans["realtime.deliver"]
    assert delivery.context is not None
    assert delivery.parent is not None
    assert delivery.context.trace_id == parent.get_span_context().trace_id
    assert delivery.parent.span_id == parent.get_span_context().span_id
    provider.shutdown()
