from __future__ import annotations

import httpx
import pytest
import sentry_sdk
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.context import attach, detach
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import (
    NonRecordingSpan,
    SpanContext,
    TraceFlags,
    TraceState,
    set_span_in_context,
)
from sentry_sdk.envelope import Envelope
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.transport import Transport
from sentry_sdk.types import Event

from src.config import ObservabilityConfig
from src.errors import ErrorCode
from src.main import app_error_handler, unhandled_exception_handler
from src.observability.context import bind_context, clear_context
from src.observability.middleware import RequestContextMiddleware
from src.observability.propagation import capture_outbox_context, extract_outbox_context
from src.observability.sentry import before_send, capture_exception_once
from src.observability.tracing import _sanitize_async_httpx_request_span, build_tracer_provider
from src.shared.errors import AppError, BadRequestError, DatabaseError

pytestmark = pytest.mark.no_infra


def _provider(rate: float) -> tuple[TracerProvider, InMemorySpanExporter]:
    config = ObservabilityConfig(
        environment="test",
        tracing_enabled=True,
        sampling_rate=rate,
    )
    exporter = InMemorySpanExporter()
    provider = build_tracer_provider(config, exporter=exporter)
    return provider, exporter


def test_sampling_one_records_every_root_span() -> None:
    provider, exporter = _provider(1.0)
    tracer = provider.get_tracer(__name__)
    for index in range(20):
        with tracer.start_as_current_span(f"operation-{index}"):
            pass
    provider.force_flush()

    assert len(exporter.get_finished_spans()) == 20
    provider.shutdown()


def test_parent_based_sampler_preserves_sampled_and_unsampled_parent() -> None:
    provider, exporter = _provider(0.0)
    tracer = provider.get_tracer(__name__)

    sampled_parent = SpanContext(
        trace_id=1,
        span_id=1,
        is_remote=True,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
        trace_state=TraceState(),
    )
    token = attach(set_span_in_context(NonRecordingSpan(sampled_parent)))
    try:
        with tracer.start_as_current_span("sampled-child"):
            pass
    finally:
        detach(token)

    unsampled_parent = SpanContext(
        trace_id=2,
        span_id=2,
        is_remote=True,
        trace_flags=TraceFlags(TraceFlags.DEFAULT),
        trace_state=TraceState(),
    )
    token = attach(set_span_in_context(NonRecordingSpan(unsampled_parent)))
    try:
        with tracer.start_as_current_span("unsampled-child"):
            pass
    finally:
        detach(token)

    provider.force_flush()
    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == ["sampled-child"]
    assert spans[0].context is not None
    assert spans[0].context.trace_id == sampled_parent.trace_id
    provider.shutdown()


@pytest.mark.asyncio
async def test_async_http_span_drops_query_parameters() -> None:
    from opentelemetry.instrumentation.httpx import RequestInfo

    class RecordingSpan:
        def __init__(self) -> None:
            self.attributes: dict[str, object] = {}

        def is_recording(self) -> bool:
            return True

        def set_attribute(self, key: str, value: object) -> None:
            self.attributes[key] = value

    span = RecordingSpan()
    request = RequestInfo(
        method=b"GET",
        url=httpx.URL("https://provider.test/callback?token=secret-marker"),
        headers=None,
        stream=None,
        extensions=None,
    )

    await _sanitize_async_httpx_request_span(span, request)  # type: ignore[arg-type]

    assert span.attributes["url.full"] == "https://provider.test/callback"
    assert span.attributes["http.url"] == "https://provider.test/callback"
    assert "secret-marker" not in str(span.attributes)


def test_sentry_event_scrubs_secrets_query_and_task_arguments() -> None:
    event: Event = {
        "request": {
            "url": "https://example.test/path?token=secret-marker",
            "headers": {"Authorization": "Bearer secret-marker", "Accept": "json"},
        },
        "contexts": {
            "celery-job": {
                "args": ["secret-marker"],
                "kwargs": {"token": "secret-marker"},
            }
        },
        "exception": {
            "values": [
                {
                    "type": "ProviderError",
                    "value": (
                        "failed https://example.test/path?token=secret-marker "
                        "with Bearer secret-marker"
                    ),
                }
            ]
        },
    }

    sanitized = before_send(event, {})

    assert sanitized is not None
    serialized = str(sanitized)
    assert "secret-marker" not in serialized
    request = sanitized.get("request")
    assert request is not None
    assert request["url"] == "https://example.test/path"


def test_sentry_sdk_transport_receives_one_correlated_sanitized_event() -> None:
    events: list[Event] = []

    class RecordingTransport(Transport):
        def capture_envelope(self, envelope: Envelope) -> None:
            event = envelope.get_event()
            if event is not None:
                events.append(event)

    transport = RecordingTransport()
    client = sentry_sdk.Client(
        dsn="http://public@example.invalid/1",
        transport=transport,
        default_integrations=False,
        before_send=before_send,
        include_local_variables=False,
    )
    span_context = SpanContext(
        trace_id=0x123,
        span_id=0x456,
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
        trace_state=TraceState(),
    )
    otel_token = attach(set_span_in_context(NonRecordingSpan(span_context)))
    bound = bind_context(request_id="request-sdk-transport")
    try:
        with sentry_sdk.isolation_scope() as scope:
            scope.set_client(client)
            scope.add_breadcrumb(
                category="http",
                data={
                    "url": "https://provider.test/email?token=secret-marker",
                    "authorization": "Bearer secret-marker",
                },
            )
            error = RuntimeError("provider request failed")
            capture_exception_once(error)
            capture_exception_once(error)
            client.flush(timeout=1)
    finally:
        clear_context(bound)
        detach(otel_token)
        client.close(timeout=1)

    assert len(events) == 1
    event = events[0]
    tags = event.get("tags")
    assert tags is not None
    assert tags["request_id"] == "request-sdk-transport"
    assert tags["otel_trace_id"] == format(span_context.trace_id, "032x")
    assert "secret-marker" not in str(event)


def test_outbox_context_round_trip_and_malformed_fallback() -> None:
    provider, _ = _provider(1.0)
    tracer = provider.get_tracer(__name__)
    bound = bind_context(request_id="request-123")
    try:
        with tracer.start_as_current_span("registration") as span:
            captured = capture_outbox_context()
            assert captured is not None
            extracted = extract_outbox_context(captured)
            assert extracted.valid is True
            assert extracted.request_id == "request-123"
            parent = trace.get_current_span(extracted.context).get_span_context()
            assert parent.trace_id == span.get_span_context().trace_id
    finally:
        clear_context(bound)
        provider.shutdown()

    malformed = extract_outbox_context(
        {"traceparent": "not-a-traceparent", "request_id": "request-legacy"}
    )
    assert malformed.valid is False
    assert malformed.context is None
    assert malformed.request_id == "request-legacy"
    assert extract_outbox_context(None).valid is True


def test_sentry_capture_uses_root_cause_and_deduplicates(monkeypatch) -> None:
    captured: list[BaseException] = []
    monkeypatch.setattr("sentry_sdk.capture_exception", captured.append)

    root = ValueError("database unavailable")
    wrapped = RuntimeError("operation failed")
    wrapped.__cause__ = root
    bound = bind_context(request_id="request-sentry")
    try:
        capture_exception_once(wrapped)
        capture_exception_once(wrapped)
        capture_exception_once(root)
    finally:
        clear_context(bound)

    assert captured == [root]


def test_fastapi_error_boundaries_capture_5xx_once_and_ignore_4xx(monkeypatch) -> None:
    captured: list[BaseException] = []
    monkeypatch.setattr(sentry_sdk, "capture_exception", captured.append)

    app = FastAPI()
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.get("/expected")
    async def expected_error() -> None:
        raise BadRequestError(ErrorCode.INVALID_CREDENTIALS)

    @app.get("/database")
    async def database_error() -> None:
        root = ValueError("database-secret-free-root")
        raise DatabaseError() from root

    @app.get("/unhandled")
    async def unhandled_error() -> None:
        raise RuntimeError("unhandled-root")

    with TestClient(
        RequestContextMiddleware(app),
        raise_server_exceptions=False,
    ) as client:
        expected = client.get("/expected")
        database = client.get("/database")
        unhandled = client.get("/unhandled")

    assert expected.status_code == 400
    assert expected.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert database.status_code == 500
    assert database.json()["error"]["code"] == "DATABASE_ERROR"
    assert unhandled.status_code == 500
    assert unhandled.json()["error"]["code"] == "UNKNOWN_ERROR"
    assert all(response.headers["x-request-id"] for response in (expected, database, unhandled))
    assert len(captured) == 1
    assert isinstance(captured[0], ValueError)


def test_fastapi_sentry_sdk_emits_one_event_per_5xx_and_none_for_4xx() -> None:
    events: list[Event] = []

    class RecordingTransport(Transport):
        def capture_envelope(self, envelope: Envelope) -> None:
            event = envelope.get_event()
            if event is not None:
                events.append(event)

    client = sentry_sdk.Client(
        dsn="http://public@example.invalid/1",
        transport=RecordingTransport(),
        integrations=[
            FastApiIntegration(),
            LoggingIntegration(level=None, event_level=None),
        ],
        default_integrations=True,
        before_send=before_send,
        traces_sample_rate=0.0,
        include_local_variables=False,
        max_request_body_size="never",
    )
    app = FastAPI()
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.get("/expected")
    async def expected_error() -> None:
        raise BadRequestError(ErrorCode.INVALID_CREDENTIALS)

    @app.get("/database")
    async def database_error() -> None:
        root = ValueError("database unavailable")
        raise DatabaseError() from root

    @app.get("/unhandled")
    async def unhandled_error() -> None:
        raise RuntimeError("unhandled failure")

    try:
        with sentry_sdk.isolation_scope() as scope:
            scope.set_client(client)
            with TestClient(
                RequestContextMiddleware(app),
                raise_server_exceptions=False,
            ) as test_client:
                assert test_client.get("/expected").status_code == 400
                assert test_client.get("/database").status_code == 500
                assert test_client.get("/unhandled").status_code == 500
            client.flush(timeout=1)
    finally:
        client.close(timeout=1)

    assert len(events) == 2
    exception_types: set[str] = set()
    for event in events:
        exception = event.get("exception")
        if exception is None:
            continue
        values = exception.get("values")
        if values:
            exception_types.add(values[-1]["type"])
    assert exception_types == {"ValueError", "RuntimeError"}


def test_celery_sentry_sdk_ignores_retry_and_captures_final_failure_once(
    monkeypatch,
) -> None:
    from celery.exceptions import Retry

    from src.registration import tasks
    from src.registration.email_gateway import TransientEmailGatewayError

    events: list[Event] = []

    class RecordingTransport(Transport):
        def capture_envelope(self, envelope: Envelope) -> None:
            event = envelope.get_event()
            if event is not None:
                events.append(event)

    client = sentry_sdk.Client(
        dsn="http://public@example.invalid/1",
        transport=RecordingTransport(),
        integrations=[
            CeleryIntegration(),
            LoggingIntegration(level=None, event_level=None),
        ],
        default_integrations=False,
        before_send=before_send,
        traces_sample_rate=0.0,
        include_local_variables=False,
    )

    def transient(coroutine) -> None:
        coroutine.close()
        raise TransientEmailGatewayError("provider unavailable")

    def permanent(coroutine) -> None:
        coroutine.close()
        raise RuntimeError("permanent provider failure")

    try:
        with sentry_sdk.isolation_scope() as scope:
            scope.set_client(client)
            monkeypatch.setattr(tasks, "_run_in_worker_loop", transient)
            with pytest.raises(Retry):
                tasks.send_verification_email.apply(
                    args=(42, "secret-marker"),
                    throw=True,
                )
            client.flush(timeout=1)
            assert events == []

            monkeypatch.setattr(tasks, "_run_in_worker_loop", permanent)
            failure_result = tasks.send_verification_email.apply(
                args=(42, "secret-marker"),
                throw=False,
            )
            client.flush(timeout=1)
            assert failure_result.state == "FAILURE"
    finally:
        client.close(timeout=1)

    assert len(events) == 1
    assert "RuntimeError" in str(events[0].get("exception"))
    assert "secret-marker" not in str(events[0])
