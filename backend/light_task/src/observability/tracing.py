from __future__ import annotations

import socket
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor, RequestInfo
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Span, Status, StatusCode

from src.config import ObservabilityConfig

_instrumented_httpx = False
_instrumented_redis = False


class BoundedBatchSpanProcessor(BatchSpanProcessor):
    """Drain and stop the exporter within the process shutdown budget."""

    def shutdown(self) -> None:
        self._batch_processor.shutdown(timeout_millis=2500)


def build_tracer_provider(
    config: ObservabilityConfig,
    *,
    exporter: SpanExporter | None = None,
) -> TracerProvider:
    provider = TracerProvider(
        sampler=ParentBased(TraceIdRatioBased(config.sampling_rate)),
        resource=Resource.create(
            {
                "service.name": config.service_name,
                "service.version": config.version,
                "service.instance.id": socket.gethostname(),
                "deployment.environment.name": config.environment,
            }
        ),
    )
    span_exporter = exporter or OTLPSpanExporter(
        endpoint=config.otlp_endpoint,
        timeout=5,
    )
    provider.add_span_processor(
        BoundedBatchSpanProcessor(
            span_exporter,
            max_queue_size=2048,
            max_export_batch_size=256,
            schedule_delay_millis=5000,
            export_timeout_millis=5000,
        )
    )
    return provider


def set_global_tracer_provider(provider: TracerProvider) -> None:
    current = trace.get_tracer_provider()
    if isinstance(current, TracerProvider):
        return
    trace.set_tracer_provider(provider)


def instrument_http_clients(provider: TracerProvider) -> None:
    global _instrumented_httpx, _instrumented_redis
    if not _instrumented_httpx:
        HTTPXClientInstrumentor().instrument(
            tracer_provider=provider,
            request_hook=_sanitize_httpx_request_span,
            async_request_hook=_sanitize_async_httpx_request_span,
        )
        _instrumented_httpx = True
    if not _instrumented_redis:
        RedisInstrumentor().instrument(
            tracer_provider=provider,
            request_hook=_sanitize_redis_span,
        )
        _instrumented_redis = True


def _sanitize_httpx_request_span(span: Span, request: RequestInfo) -> None:
    if not span.is_recording():
        return
    parts = urlsplit(str(request.url))
    clean_url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    span.set_attribute("url.full", clean_url)
    span.set_attribute("http.url", clean_url)


async def _sanitize_async_httpx_request_span(span: Span, request: RequestInfo) -> None:
    _sanitize_httpx_request_span(span, request)


def _sanitize_redis_span(
    span: Span,
    _: Any,
    args: Sequence[Any],
    __: dict[str, Any],
) -> None:
    if not span.is_recording():
        return
    command = str(args[0]).upper() if args else "UNKNOWN"
    span.set_attribute("db.statement", command)
    span.set_attribute("db.query.text", command)
    span.set_attribute("db.redis.args_length", len(args))


def mark_current_span_error(exc: BaseException | None = None) -> None:
    span = trace.get_current_span()
    if not span.is_recording():
        return
    span.set_status(Status(StatusCode.ERROR))
    if exc is not None:
        span.record_exception(exc)


def set_current_span_attribute(name: str, value: str | bool | int | float) -> None:
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute(name, value)


def get_tracer(name: str):
    return trace.get_tracer(name)
