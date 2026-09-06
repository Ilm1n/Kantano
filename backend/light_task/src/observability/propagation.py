from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from opentelemetry import propagate, trace
from opentelemetry.context import Context

from src.observability.context import get_request_id


@dataclass(frozen=True)
class ExtractedOutboxContext:
    context: Context | None
    request_id: str | None
    valid: bool


def capture_outbox_context() -> dict[str, str] | None:
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    captured = {
        key: value for key, value in carrier.items() if key.lower() in {"traceparent", "tracestate"}
    }
    request_id = get_request_id()
    if request_id:
        captured["request_id"] = request_id
    return captured or None


def extract_outbox_context(value: Any) -> ExtractedOutboxContext:
    if value is None:
        return ExtractedOutboxContext(context=None, request_id=None, valid=True)
    if not isinstance(value, dict):
        return ExtractedOutboxContext(context=None, request_id=None, valid=False)

    request_id_value = value.get("request_id")
    request_id = request_id_value if isinstance(request_id_value, str) else None
    carrier = {
        key: item
        for key, item in value.items()
        if key in {"traceparent", "tracestate"} and isinstance(item, str)
    }
    if "traceparent" not in carrier:
        return ExtractedOutboxContext(
            context=None,
            request_id=request_id,
            valid=not any(key in value for key in ("traceparent", "tracestate")),
        )

    context = propagate.extract(carrier)
    span_context = trace.get_current_span(context).get_span_context()
    if not span_context.is_valid:
        return ExtractedOutboxContext(context=None, request_id=request_id, valid=False)
    return ExtractedOutboxContext(context=context, request_id=request_id, valid=True)
