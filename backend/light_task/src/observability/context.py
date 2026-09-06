from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

import structlog
from opentelemetry import trace

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


@dataclass(frozen=True)
class BoundContext:
    request_token: Token[str | None] | None
    structlog_tokens: Mapping[str, Token[Any]]


def get_request_id() -> str | None:
    return _request_id.get()


def bind_context(**values: Any) -> BoundContext:
    clean_values = {key: value for key, value in values.items() if value is not None}
    request_token = None
    if "request_id" in clean_values:
        request_token = _request_id.set(str(clean_values["request_id"]))
    structlog_tokens = structlog.contextvars.bind_contextvars(**clean_values)
    return BoundContext(request_token=request_token, structlog_tokens=structlog_tokens)


def clear_context(bound: BoundContext | None = None) -> None:
    if bound:
        if bound.request_token is not None:
            _request_id.reset(bound.request_token)
        structlog.contextvars.reset_contextvars(**bound.structlog_tokens)
    else:
        _request_id.set(None)
        structlog.contextvars.clear_contextvars()


@contextmanager
def contextualize(**values: Any):
    tokens = bind_context(**values)
    try:
        yield
    finally:
        clear_context(tokens)


def add_trace_context(
    _: Any,
    __: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        event_dict["trace_id"] = format(span_context.trace_id, "032x")
        event_dict["span_id"] = format(span_context.span_id, "016x")
        event_dict["trace_sampled"] = span_context.trace_flags.sampled
    return event_dict
