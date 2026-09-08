from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from opentelemetry import propagate, trace
from opentelemetry.context import Context

from src.observability.context import get_request_id


@dataclass(frozen=True)
class ExtractedTraceContext:
    context: Context | None
    request_id: str | None
    valid: bool


def capture_trace_context() -> dict[str, str] | None:
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    captured = {
        key: value for key, value in carrier.items() if key.lower() in {"traceparent", "tracestate"}
    }
    request_id = get_request_id()
    if request_id:
        captured["request_id"] = request_id
    return captured or None


def extract_trace_context(value: Any) -> ExtractedTraceContext:
    if value is None:
        return ExtractedTraceContext(context=None, request_id=None, valid=True)
    if not isinstance(value, dict):
        return ExtractedTraceContext(context=None, request_id=None, valid=False)

    request_id_value = value.get("request_id")
    request_id = request_id_value if isinstance(request_id_value, str) else None
    carrier = {
        key: item
        for key, item in value.items()
        if key in {"traceparent", "tracestate"} and isinstance(item, str)
    }
    if "traceparent" not in carrier:
        return ExtractedTraceContext(
            context=None,
            request_id=request_id,
            valid=not any(key in value for key in ("traceparent", "tracestate")),
        )

    context = propagate.extract(carrier)
    span_context = trace.get_current_span(context).get_span_context()
    if not span_context.is_valid:
        return ExtractedTraceContext(context=None, request_id=request_id, valid=False)
    return ExtractedTraceContext(context=context, request_id=request_id, valid=True)


def capture_outbox_context() -> dict[str, str] | None:
    return capture_trace_context()


def extract_outbox_context(value: Any) -> ExtractedTraceContext:
    return extract_trace_context(value)
