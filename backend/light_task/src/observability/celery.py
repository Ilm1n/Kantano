from __future__ import annotations

import time
from typing import Any

from celery import signals
from opentelemetry.instrumentation.celery import CeleryInstrumentor, utils as celery_utils
from opentelemetry.trace import Status, StatusCode

from src.observability.context import BoundContext, bind_context, clear_context
from src.observability.metrics import get_active_metrics

_task_contexts: dict[str, BoundContext] = {}
_task_started_at: dict[str, float] = {}
_signals_connected = False


class KantanoCeleryInstrumentor(CeleryInstrumentor):
    """Work around Celery 5.6 passing a Kombu Exchange during retry publish."""

    def _trace_before_publish(self, *args: Any, **kwargs: Any) -> None:
        exchange = kwargs.get("exchange")
        if exchange is not None and not isinstance(
            exchange,
            (bool, str, bytes, int, float),
        ):
            kwargs = {
                **kwargs,
                "exchange": str(getattr(exchange, "name", exchange)),
            }
        super()._trace_before_publish(*args, **kwargs)

    @staticmethod
    def _trace_retry(*args: Any, **kwargs: Any) -> None:
        """Represent every retry as a failed attempt, not a successful run."""

        CeleryInstrumentor._trace_retry(*args, **kwargs)
        task = celery_utils.retrieve_task_from_sender(kwargs)
        task_id = celery_utils.retrieve_task_id_from_request(kwargs)
        if task is None or task_id is None:
            return
        context = celery_utils.retrieve_context(task, task_id)
        if context is None:
            return
        span, _, _ = context
        if span.is_recording():
            # The upstream integration already records the retry reason.  Only
            # set status here so the same exception/stack is not recorded twice.
            span.set_status(Status(StatusCode.ERROR, "task retry"))


def _preserve_application_logging(**_: Any) -> None:
    """Tell Celery that logging is already configured by Structlog."""


def connect_celery_context_signals() -> None:
    global _signals_connected
    if _signals_connected:
        return
    signals.setup_logging.connect(
        _preserve_application_logging,
        weak=False,
        dispatch_uid="kantano-observability-setup-logging",
    )
    signals.task_prerun.connect(
        _task_prerun,
        weak=False,
        dispatch_uid="kantano-observability-task-prerun",
    )
    signals.task_postrun.connect(
        _task_postrun,
        weak=False,
        dispatch_uid="kantano-observability-task-postrun",
    )
    signals.task_failure.connect(
        _task_failure,
        weak=False,
        dispatch_uid="kantano-observability-task-failure",
    )
    _signals_connected = True


def _task_prerun(
    task_id: str | None = None,
    task: Any = None,
    **_: Any,
) -> None:
    if not task_id:
        return
    clear_context()
    request = getattr(task, "request", None)
    headers = getattr(request, "headers", None) or {}
    retries = int(getattr(request, "retries", 0))
    _task_contexts[task_id] = bind_context(
        request_id=headers.get("request_id"),
        task_id=task_id,
        outbox_event_id=headers.get("outbox_event_id"),
        attempt=retries + 1,
    )
    _task_started_at[task_id] = time.perf_counter()


def _task_postrun(
    task_id: str | None = None,
    task: Any = None,
    state: str | None = None,
    **_: Any,
) -> None:
    if not task_id:
        clear_context()
        return
    metrics = get_active_metrics()
    task_name = str(getattr(task, "name", "unknown"))
    started_at = _task_started_at.pop(task_id, None)
    if metrics is not None:
        result = {
            "SUCCESS": "success",
            "RETRY": "retry",
            "FAILURE": "failure",
            "REVOKED": "revoked",
        }.get(state or "", "unknown")
        metrics.celery_attempts_total.labels(task=task_name, result=result).inc()
        if started_at is not None:
            metrics.celery_attempt_duration.labels(task=task_name).observe(
                time.perf_counter() - started_at
            )
    clear_context(_task_contexts.pop(task_id, None))


def _task_failure(sender: Any = None, **_: Any) -> None:
    metrics = get_active_metrics()
    if metrics is not None:
        task_name = str(getattr(sender, "name", "unknown"))
        metrics.celery_final_failures_total.labels(task=task_name).inc()
