from __future__ import annotations

from typing import Annotated

from fastapi import Header, HTTPException, Request, WebSocket, status

from src.realtimev1.publisher import DomainEventPublisher
from src.realtimev1.runtime import RealtimeRuntime


def _resolve_runtime(app_state: object) -> RealtimeRuntime:
    runtime = getattr(app_state, "realtime_runtime", None)
    if not runtime:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="REALTIME_RUNTIME_UNAVAILABLE",
        )
    return runtime


def get_realtime_runtime(request: Request) -> RealtimeRuntime:
    return _resolve_runtime(request.app.state)


def get_realtime_runtime_from_ws(websocket: WebSocket) -> RealtimeRuntime:
    return _resolve_runtime(websocket.app.state)


def get_event_publisher(request: Request) -> DomainEventPublisher:
    runtime = getattr(request.app.state, "realtime_runtime", None)
    return DomainEventPublisher(runtime=runtime)


def get_client_mutation_id(
    x_client_mutation_id: Annotated[str | None, Header(alias="X-Client-Mutation-Id")] = None,
) -> str | None:
    if not x_client_mutation_id:
        return None
    value = x_client_mutation_id.strip()
    return value or None
