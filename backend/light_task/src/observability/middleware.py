from __future__ import annotations

import time
from uuid import uuid4

from opentelemetry.instrumentation.utils import suppress_instrumentation
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.logger import get_logger
from src.observability.context import bind_context, clear_context

logger = get_logger("src.http.access")

_QUIET_SUCCESS_PATHS = {"/api/health", "/api/health/ready", "/metrics"}
_SUPPRESSED_PATH_PREFIXES = (
    "/api/health",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/local-storage",
)


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    def __getattr__(self, name: str):
        return getattr(self.app, name)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            connection_id = str(uuid4())
            tokens = bind_context(connection_id=connection_id)
            logger.info(
                "WebSocket connection started",
                extra={"websocket_path": scope.get("path")},
            )
            try:
                await self.app(scope, receive, send)
            finally:
                logger.info(
                    "WebSocket connection stopped",
                    extra={"websocket_path": scope.get("path")},
                )
                clear_context(tokens)
            return
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid4())
        tokens = bind_context(request_id=request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            path = str(scope.get("path", ""))
            if path.startswith(_SUPPRESSED_PATH_PREFIXES):
                with suppress_instrumentation():
                    await self.app(scope, receive, send_with_request_id)
            else:
                await self.app(scope, receive, send_with_request_id)
        finally:
            clear_context(tokens)


class AccessLogMiddleware:
    """Emit one access log while the OpenTelemetry server span is still active."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status_code = 500

        async def capture_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        path = str(scope.get("path", ""))
        try:
            await self.app(scope, receive, capture_status)
        finally:
            duration_seconds = time.perf_counter() - started
            route = scope.get("route")
            route_template = getattr(route, "path", None) or "__unmatched__"
            if status_code >= 400 or path not in _QUIET_SUCCESS_PATHS:
                logger.info(
                    "HTTP request completed",
                    extra={
                        "http_method": scope.get("method"),
                        "http_route": route_template,
                        "http_status_code": status_code,
                        "duration_seconds": round(duration_seconds, 6),
                    },
                )
