from __future__ import annotations

import logging
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.types import Event, Hint

from src.config import ObservabilityConfig
from src.observability.context import get_request_id
from src.observability.redaction import is_sensitive_key, redact_string
from src.shared.errors import AppError


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if is_sensitive_key(lowered):
                clean[key] = "[REDACTED]"
            elif lowered in {"url", "request_url"} and isinstance(item, str):
                parts = urlsplit(item)
                clean[key] = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
            else:
                clean[key] = _sanitize(item)
        return clean
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return redact_string(value)
    return value


def before_send(event: Event, hint: Hint) -> Event | None:
    # Starlette reports handled 5xx AppError wrappers before our exception
    # handler can capture their original cause. Drop only that automatic
    # wrapper event; the explicit handler emits the root cause once.
    exc_info = hint.get("exc_info")
    exception = exc_info[1] if exc_info is not None else None
    values = (event.get("exception") or {}).get("values") or []
    mechanism = values[-1].get("mechanism") if values else None
    if (
        isinstance(exception, AppError)
        and isinstance(mechanism, dict)
        and mechanism.get("type") == "starlette"
        and mechanism.get("handled") is True
    ):
        return None

    sanitized = cast(Event, _sanitize(event))
    request_id = get_request_id()
    if request_id:
        sanitized.setdefault("tags", {})["request_id"] = request_id
    from opentelemetry import trace

    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        sanitized.setdefault("tags", {})["otel_trace_id"] = format(span_context.trace_id, "032x")
    return sanitized


def initialize_sentry(config: ObservabilityConfig) -> bool:
    if not config.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=config.sentry_dsn,
        environment=config.environment,
        release=config.version,
        server_name=config.service_name,
        integrations=[
            FastApiIntegration(),
            CeleryIntegration(),
            # Application logs remain breadcrumbs, but handled log records never
            # create error events on their own. Exceptions are captured once by
            # the FastAPI/Celery integrations or the explicit 5xx boundary.
            LoggingIntegration(level=logging.INFO, event_level=None),
        ],
        traces_sample_rate=0.0,
        profiles_sample_rate=0.0,
        enable_logs=False,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        before_send=before_send,
    )
    return True


def _root_cause(exc: BaseException) -> BaseException:
    current = exc
    seen: set[int] = set()
    while id(current) not in seen:
        seen.add(id(current))
        if current.__cause__ is not None:
            current = current.__cause__
            continue
        if current.__context__ is not None and not current.__suppress_context__:
            current = current.__context__
            continue
        break
    return current


def capture_exception_once(exc: BaseException) -> None:
    root = _root_cause(exc)
    if getattr(root, "_kantano_sentry_captured", False):
        return
    root.__dict__["_kantano_sentry_captured"] = True
    sentry_sdk.capture_exception(root)


def flush_sentry(timeout: float = 2.0) -> None:
    sentry_sdk.flush(timeout=timeout)
