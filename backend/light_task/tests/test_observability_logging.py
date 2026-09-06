from __future__ import annotations

import json
import logging
from asyncio import run
from io import StringIO
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from starlette.types import Message, Receive, Scope, Send

from src.config import ObservabilityConfig
from src.observability.context import bind_context, clear_context, get_request_id
from src.observability.logging import reset_logging_for_tests, setup_logging
from src.observability.middleware import AccessLogMiddleware, RequestContextMiddleware

pytestmark = pytest.mark.no_infra


def _json_log_stream() -> StringIO:
    stream = StringIO()
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    handler.setStream(stream)
    return stream


def test_json_logging_is_structured_redacted_and_idempotent() -> None:
    reset_logging_for_tests()
    config = ObservabilityConfig(
        environment="test",
        service_name="kantano-api",
        version="test-sha",
        log_format="json",
    )
    setup_logging(config)
    setup_logging(config)
    stream = _json_log_stream()

    bound = bind_context(request_id="request-123")
    try:
        logging.getLogger("src.test").info(
            "structured event",
            extra={
                "result": "ok",
                "token": "secret-marker",
                "oauth": {"client_secret": "nested-secret-marker"},
                "data": {"kwargs": "{'token': 'task-secret-marker'}"},
                "provider_error": (
                    "POST https://provider.test/emails?token=url-secret-marker "
                    "failed with Bearer bearer-secret-marker and password=password-secret-marker"
                ),
            },
        )
    finally:
        clear_context(bound)

    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["event"] == "structured event"
    assert payload["level"] == "info"
    assert payload["logger"] == "src.test"
    assert payload["service"] == "kantano-api"
    assert payload["environment"] == "test"
    assert payload["version"] == "test-sha"
    assert payload["request_id"] == "request-123"
    assert payload["result"] == "ok"
    assert payload["token"] == "[REDACTED]"
    assert payload["oauth"]["client_secret"] == "[REDACTED]"
    assert payload["data"]["kwargs"] == "[REDACTED]"
    assert "secret-marker" not in lines[0]
    assert payload["timestamp"].endswith("Z")
    assert get_request_id() is None


@pytest.mark.parametrize(
    ("override", "error"),
    [
        ({"tracing_enabled": False}, "Tracing must be enabled"),
        ({"metrics_enabled": False}, "Metrics must be enabled"),
        ({"log_format": "console"}, "JSON logging must be enabled"),
        ({"sentry_dsn": ""}, "Sentry DSN is required"),
    ],
)
def test_production_observability_rejects_missing_required_signals(
    override: dict[str, object],
    error: str,
) -> None:
    config: dict[str, object] = {
        "environment": "production",
        "service_name": "kantano-api",
        "version": "test-sha",
        "log_format": "json",
        "tracing_enabled": True,
        "metrics_enabled": True,
        "sentry_dsn": "https://public@example.invalid/1",
    }
    config.update(override)

    with pytest.raises(ValueError, match=error):
        ObservabilityConfig.model_validate(config)


def test_request_id_is_returned_for_2xx_4xx_and_5xx() -> None:
    app = FastAPI()

    @app.get("/ok")
    async def ok() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/missing")
    async def missing() -> None:
        raise HTTPException(status_code=404)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    wrapped = RequestContextMiddleware(app)
    with TestClient(wrapped, raise_server_exceptions=False) as client:
        responses = [client.get("/ok"), client.get("/missing"), client.get("/boom")]

    assert [response.status_code for response in responses] == [200, 404, 500]
    request_ids = [response.headers.get("x-request-id") for response in responses]
    assert all(request_ids)
    assert len(set(request_ids)) == 3


def test_parallel_requests_keep_distinct_context() -> None:
    import asyncio

    seen: list[tuple[str | None, str | None]] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        before = get_request_id()
        await asyncio.sleep(0)
        after = get_request_id()
        seen.append((before, after))
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = RequestContextMiddleware(app)

    async def invoke(path: str) -> None:
        messages: list[Message] = []

        async def receive() -> Message:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: Message) -> None:
            messages.append(message)

        await middleware(
            {"type": "http", "method": "GET", "path": path, "headers": []},
            receive,
            send,
        )

    async def run_parallel() -> None:
        await asyncio.gather(invoke("/one"), invoke("/two"))

    asyncio.run(run_parallel())

    assert len(seen) == 2
    assert all(before == after for before, after in seen)
    assert seen[0][0] != seen[1][0]
    assert get_request_id() is None


def test_access_log_is_emitted_inside_active_server_span() -> None:
    reset_logging_for_tests()
    setup_logging(
        ObservabilityConfig(
            environment="test",
            service_name="kantano-api",
            version="test-sha",
            log_format="json",
        )
    )
    stream = _json_log_stream()
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer(__name__)

    async def endpoint(scope: Scope, receive: Receive, send: Send) -> None:
        scope["route"] = SimpleNamespace(path="/items/{item_id}")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    access_log = AccessLogMiddleware(endpoint)

    async def traced_app(scope: Scope, receive: Receive, send: Send) -> None:
        with tracer.start_as_current_span("GET /items/{item_id}"):
            await access_log(scope, receive, send)

    middleware = RequestContextMiddleware(traced_app)

    async def invoke() -> None:
        async def receive() -> Message:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(_: Message) -> None:
            return None

        await middleware(
            {"type": "http", "method": "GET", "path": "/items/42", "headers": []},
            receive,
            send,
        )

    try:
        run(invoke())
        payload = json.loads(stream.getvalue().splitlines()[-1])
        span = exporter.get_finished_spans()[0]
        assert span.context is not None

        assert payload["event"] == "HTTP request completed"
        assert payload["http_route"] == "/items/{item_id}"
        assert payload["request_id"]
        assert payload["trace_id"] == format(span.context.trace_id, "032x")
        assert payload["span_id"] == format(span.context.span_id, "016x")
        assert payload["trace_sampled"] is True
    finally:
        provider.shutdown()
