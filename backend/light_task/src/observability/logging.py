from __future__ import annotations

import logging
import sys
from threading import Lock
from typing import Any

import structlog

from src.config import ObservabilityConfig
from src.observability.context import add_trace_context
from src.observability.redaction import is_sensitive_key, redact_string

_configured_signature: tuple[str, str, str, str, str] | None = None
_configure_lock = Lock()


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if is_sensitive_key(key) else _redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_string(value)
    return value


def redact_sensitive_data(
    _: Any,
    __: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    return _redact_value(event_dict)


def add_service_fields(config: ObservabilityConfig):
    def processor(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        event_dict.setdefault("service", config.service_name)
        event_dict.setdefault("environment", config.environment)
        event_dict.setdefault("version", config.version)
        return event_dict

    return processor


def setup_logging(config: ObservabilityConfig) -> None:
    global _configured_signature
    signature = (
        config.service_name,
        config.environment,
        config.version,
        config.log_format,
        config.log_level,
    )
    with _configure_lock:
        if _configured_signature == signature:
            return

        timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp")
        shared_processors = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.ExtraAdder(),
            add_service_fields(config),
            add_trace_context,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            redact_sensitive_data,
            timestamper,
        ]
        renderer: structlog.types.Processor = (
            structlog.processors.JSONRenderer()
            if config.log_format == "json"
            else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
        )
        formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                renderer,
            ],
        )
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)

        root = logging.getLogger()
        root.handlers.clear()
        root.addHandler(handler)
        root.setLevel(config.log_level)
        root.disabled = False

        # Uvicorn, Celery and test runners may disable already-created loggers
        # while installing their own configuration.  Re-enabling them makes
        # this application-owned setup genuinely idempotent across lifecycle
        # hooks and keeps child loggers from silently dropping records.
        for existing_logger in logging.root.manager.loggerDict.values():
            if isinstance(existing_logger, logging.Logger):
                existing_logger.disabled = False

        for logger_name in ("src", "fastapi", "uvicorn", "uvicorn.error", "celery"):
            named_logger = logging.getLogger(logger_name)
            named_logger.handlers.clear()
            named_logger.propagate = True
            named_logger.setLevel(config.log_level)
        logging.getLogger("uvicorn.access").handlers.clear()
        logging.getLogger("uvicorn.access").propagate = False
        logging.getLogger("uvicorn.access").disabled = True
        logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)

        structlog.configure(
            processors=[
                *shared_processors,
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
        _configured_signature = signature


def reset_logging_for_tests() -> None:
    global _configured_signature
    with _configure_lock:
        _configured_signature = None
