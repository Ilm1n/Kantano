from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import HTTPServer
from typing import Any, cast

from fastapi import FastAPI
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, start_http_server
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from sqlalchemy.pool import Pool
from starlette.types import ASGIApp, Receive, Scope, Send

HTTP_DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
TASK_DURATION_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60)
LLM_DURATION_BUCKETS = (0.25, 0.5, 1, 2, 5, 10, 20, 30, 60, 120)
RUN_TOKEN_BUCKETS = (500, 1000, 2500, 5000, 10000, 20000, 40000, 80000, 160000)


def is_assistant_stream(handler: str) -> bool:
    return "/assistant/conversations/" in handler and (
        handler.endswith("/runs") or handler.endswith("/decision")
    )


class _InProgressMiddleware:
    """Registry-aware workaround for instrumentator 7.1's global-registry gauge."""

    def __init__(self, app: ASGIApp, gauge: Gauge) -> None:
        self.app = app
        self.gauge = gauge

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = str(scope.get("path", ""))
        if scope["type"] != "http" or path in {"/api/health", "/api/health/ready", "/metrics"}:
            await self.app(scope, receive, send)
            return
        self.gauge.inc()
        try:
            await self.app(scope, receive, send)
        finally:
            self.gauge.dec()


@dataclass
class ApplicationMetrics:
    registry: CollectorRegistry = field(default_factory=CollectorRegistry)

    def __post_init__(self) -> None:
        self.assistant_runs = Counter(
            "kantano_assistant_runs_total",
            "Terminal assistant runs by status.",
            ("status",),
            registry=self.registry,
        )
        self.assistant_llm_calls = Counter(
            "kantano_assistant_llm_calls_total",
            "Individual LLM attempts and usage availability.",
            ("provider", "model", "result", "fallback", "usage"),
            registry=self.registry,
        )
        self.assistant_llm_duration = Histogram(
            "kantano_assistant_llm_duration_seconds",
            "Duration of individual LLM attempts.",
            ("provider", "model"),
            buckets=LLM_DURATION_BUCKETS,
            registry=self.registry,
        )
        self.assistant_tool_calls = Counter(
            "kantano_assistant_tool_calls_total",
            "Executed assistant tools by result.",
            ("tool", "result"),
            registry=self.registry,
        )
        self.assistant_tokens = Counter(
            "kantano_assistant_tokens_total",
            "Provider-reported input and output tokens.",
            ("provider", "model", "direction"),
            registry=self.registry,
        )
        self.assistant_run_tokens = Histogram(
            "kantano_assistant_run_tokens",
            "Total tokens of fully accounted terminal runs.",
            ("mode",),
            buckets=RUN_TOKEN_BUCKETS,
            registry=self.registry,
        )
        self.outbox_unpublished = Gauge(
            "kantano_outbox_unpublished_events",
            "Current number of unpublished outbox events.",
            registry=self.registry,
        )
        self.outbox_oldest_created_timestamp = Gauge(
            "kantano_outbox_oldest_created_timestamp_seconds",
            "Creation time of the oldest unpublished outbox event as Unix time.",
            registry=self.registry,
        )
        self.outbox_publish_total = Counter(
            "kantano_outbox_publish_total",
            "Outbox publication attempts by result.",
            ("result",),
            registry=self.registry,
        )
        self.publisher_last_poll_timestamp = Gauge(
            "kantano_outbox_publisher_last_poll_timestamp_seconds",
            "Unix time of the last successful publisher poll.",
            registry=self.registry,
        )
        self.publisher_last_stats_update_timestamp = Gauge(
            "kantano_outbox_stats_last_update_timestamp_seconds",
            "Unix time of the last successful outbox aggregate update.",
            registry=self.registry,
        )
        self.celery_attempts_total = Counter(
            "kantano_celery_task_attempts_total",
            "Celery task attempts by task and result.",
            ("task", "result"),
            registry=self.registry,
        )
        self.celery_final_failures_total = Counter(
            "kantano_celery_task_final_failures_total",
            "Final Celery task failures by task.",
            ("task",),
            registry=self.registry,
        )
        self.celery_attempt_duration = Histogram(
            "kantano_celery_task_attempt_duration_seconds",
            "Duration of individual Celery task attempts.",
            ("task",),
            buckets=TASK_DURATION_BUCKETS,
            registry=self.registry,
        )
        self.realtime_connections = Gauge(
            "kantano_realtime_connections",
            "Current WebSocket connections by stable connection kind.",
            ("kind",),
            registry=self.registry,
        )
        self.realtime_errors_total = Counter(
            "kantano_realtime_errors_total",
            "Realtime publication and delivery errors.",
            ("operation",),
            registry=self.registry,
        )
        self.cache_operations_total = Counter(
            "kantano_cache_operations_total",
            "Cache operations by cache, operation, and result.",
            ("cache", "operation", "result"),
            registry=self.registry,
        )
        self.db_pool_checked_out = Gauge(
            "kantano_db_pool_checked_out_connections",
            "Currently checked out SQLAlchemy pool connections.",
            registry=self.registry,
        )
        self.db_pool_size = Gauge(
            "kantano_db_pool_size_connections",
            "Configured SQLAlchemy pool size.",
            registry=self.registry,
        )
        self.db_pool_available = Gauge(
            "kantano_db_pool_available_connections",
            "Immediately available SQLAlchemy pool capacity.",
            registry=self.registry,
        )
        self.http_requests_inprogress = Gauge(
            "http_requests_inprogress",
            "Number of HTTP requests in progress.",
            registry=self.registry,
        )
        self._instrumentator: Instrumentator | None = None
        self._metrics_server: HTTPServer | None = None
        self._metrics_thread: threading.Thread | None = None

    def instrument_fastapi(self, app: FastAPI) -> None:
        if self._instrumentator is not None:
            return
        instrumentator = Instrumentator(
            should_group_status_codes=True,
            should_ignore_untemplated=False,
            should_group_untemplated=True,
            should_instrument_requests_inprogress=False,
            excluded_handlers=[r"^/api/health(?:/ready)?$", r"^/metrics$"],
            registry=self.registry,
        )
        request_counter = metrics.requests(
            should_include_handler=False,
            should_include_method=False,
            should_include_status=True,
            registry=self.registry,
        )
        latency = metrics.latency(
            should_include_handler=True,
            should_include_method=False,
            should_include_status=False,
            buckets=HTTP_DURATION_BUCKETS,
            registry=self.registry,
        )
        if request_counter is not None:
            instrumentator.add(request_counter)
        if latency is not None:

            def ordinary_api_latency(info: metrics.Info) -> None:
                if not is_assistant_stream(info.modified_handler):
                    latency(info)

            instrumentator.add(ordinary_api_latency)
        instrumentator.instrument(app).expose(app, include_in_schema=False)
        app.add_middleware(_InProgressMiddleware, gauge=self.http_requests_inprogress)
        self._instrumentator = instrumentator

    def bind_db_pool(self, pool: Pool) -> None:
        pool_size = getattr(pool, "size", None)
        checkedout = getattr(pool, "checkedout", None)
        overflow = getattr(pool, "overflow", None)
        if not all(callable(value) for value in (pool_size, checkedout, overflow)):
            return
        pool_size_fn = cast(Callable[[], float], pool_size)
        checkedout_fn = cast(Callable[[], float], checkedout)
        overflow_fn = cast(Callable[[], float], overflow)

        self.db_pool_size.set_function(pool_size_fn)
        self.db_pool_checked_out.set_function(checkedout_fn)

        def available() -> float:
            size = float(pool_size_fn())
            in_use = float(checkedout_fn())
            current_overflow = max(float(overflow_fn()), 0.0)
            return max(size + current_overflow - in_use, 0.0)

        self.db_pool_available.set_function(available)

    def start_server(self, port: int) -> None:
        if self._metrics_server is not None:
            return
        server, thread = start_http_server(
            port,
            addr="0.0.0.0",  # noqa: S104 - reachable only on the internal Docker network.
            registry=self.registry,
        )
        self._metrics_server = server
        self._metrics_thread = thread

    def stop_server(self) -> None:
        if self._metrics_server is not None:
            self._metrics_server.shutdown()
            self._metrics_server.server_close()
            self._metrics_server = None
        if self._metrics_thread is not None:
            self._metrics_thread.join(timeout=0.5)
            self._metrics_thread = None

    def record_outbox_publish(self, result: str) -> None:
        self.outbox_publish_total.labels(result=result).inc()

    def record_publisher_poll(self) -> None:
        self.publisher_last_poll_timestamp.set(time.time())

    def update_outbox_stats(self, *, count: int, oldest_timestamp: float | None) -> None:
        self.outbox_unpublished.set(count)
        if oldest_timestamp is None:
            self.outbox_oldest_created_timestamp.set(0)
        else:
            self.outbox_oldest_created_timestamp.set(oldest_timestamp)
        self.publisher_last_stats_update_timestamp.set(time.time())


_active_metrics: ApplicationMetrics | None = None


def set_active_metrics(value: ApplicationMetrics | None) -> None:
    global _active_metrics
    _active_metrics = value


def get_active_metrics() -> ApplicationMetrics | None:
    return _active_metrics


def record_realtime_connection(kind: str, delta: int) -> None:
    if _active_metrics is not None:
        _active_metrics.realtime_connections.labels(kind=kind).inc(delta)


def record_realtime_error(operation: str) -> None:
    if _active_metrics is not None:
        _active_metrics.realtime_errors_total.labels(operation=operation).inc()


def record_cache_operation(cache: str, operation: str, result: str) -> None:
    if _active_metrics is not None:
        _active_metrics.cache_operations_total.labels(
            cache=cache,
            operation=operation,
            result=result,
        ).inc()


def record_assistant_run(status: str) -> None:
    if _active_metrics is not None:
        _active_metrics.assistant_runs.labels(status=status).inc()


def record_assistant_llm_call(
    provider: str,
    model: str,
    result: str,
    fallback: bool,
    duration: float,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> None:
    if _active_metrics is None:
        return
    reported = input_tokens is not None and output_tokens is not None
    _active_metrics.assistant_llm_calls.labels(
        provider=provider,
        model=model,
        result=result,
        fallback=str(fallback).lower(),
        usage="reported" if reported else "missing",
    ).inc()
    _active_metrics.assistant_llm_duration.labels(provider=provider, model=model).observe(duration)
    if input_tokens is not None and output_tokens is not None:
        for direction, count in (("input", input_tokens), ("output", output_tokens)):
            _active_metrics.assistant_tokens.labels(
                provider=provider,
                model=model,
                direction=direction,
            ).inc(count)


def record_assistant_tool(tool: str, result: str) -> None:
    if _active_metrics is not None:
        _active_metrics.assistant_tool_calls.labels(tool=tool, result=result).inc()


def record_assistant_run_tokens(mode: str, tokens: int) -> None:
    if _active_metrics is not None:
        _active_metrics.assistant_run_tokens.labels(mode=mode).observe(tokens)


def metric_value(metric: Any, labels: dict[str, str] | None = None) -> float:
    child = metric.labels(**labels) if labels else metric
    value: Callable[[], float] = child._value.get
    return value()
