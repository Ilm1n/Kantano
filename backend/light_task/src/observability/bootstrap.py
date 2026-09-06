from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from threading import Lock

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy.engine import Engine

from src.config import ObservabilityConfig
from src.observability.celery import (
    KantanoCeleryInstrumentor,
    connect_celery_context_signals,
)
from src.observability.logging import setup_logging
from src.observability.metrics import ApplicationMetrics, set_active_metrics
from src.observability.sentry import flush_sentry, initialize_sentry
from src.observability.tracing import (
    build_tracer_provider,
    instrument_http_clients,
    set_global_tracer_provider,
)

_runtime: ObservabilityRuntime | None = None
_runtime_lock = Lock()
logger = logging.getLogger("src.observability")


@dataclass
class ObservabilityRuntime:
    config: ObservabilityConfig
    tracer_provider: TracerProvider | None = None
    sentry_enabled: bool = False
    metrics: ApplicationMetrics | None = None
    _fastapi_instrumented: bool = False
    _sqlalchemy_instrumented: bool = False
    _db_pool_metrics_bound: bool = False
    _celery_instrumented: bool = False
    _shutdown: bool = False

    def instrument_fastapi(self, app: FastAPI) -> None:
        if self.metrics is not None:
            self.metrics.instrument_fastapi(app)
        if self.tracer_provider is None or self._fastapi_instrumented:
            return
        FastAPIInstrumentor.instrument_app(
            app,
            tracer_provider=self.tracer_provider,
            excluded_urls=("api/health,metrics,docs,redoc,openapi.json,local-storage,ws/"),
            exclude_spans=["receive", "send"],
        )
        self._fastapi_instrumented = True

    def instrument_sqlalchemy(self, engine: Engine) -> None:
        if self.metrics is not None and not self._db_pool_metrics_bound:
            self.metrics.bind_db_pool(engine.pool)
            self._db_pool_metrics_bound = True
        if self.tracer_provider is not None and not self._sqlalchemy_instrumented:
            SQLAlchemyInstrumentor().instrument(
                engine=engine,
                tracer_provider=self.tracer_provider,
            )
            self._sqlalchemy_instrumented = True

    def instrument_celery(self) -> None:
        if self._celery_instrumented:
            return
        if self.tracer_provider is not None:
            KantanoCeleryInstrumentor().instrument(tracer_provider=self.tracer_provider)
        connect_celery_context_signals()
        self._celery_instrumented = True

    def start_background_metrics_server(self) -> None:
        if self.metrics is not None:
            self.metrics.start_server(self.config.background_metrics_port)

    def shutdown(self) -> None:
        if self._shutdown:
            return
        self._shutdown = True
        started_at = time.monotonic()
        if self.tracer_provider is not None:
            # BoundedBatchSpanProcessor drains its queue with a 2.5-second
            # deadline. Sentry and the metrics server use the remaining budget.
            self.tracer_provider.shutdown()
        if self.sentry_enabled:
            flush_sentry(timeout=1.5)
        if self.metrics is not None:
            self.metrics.stop_server()
        logger.info(
            "Observability shutdown completed",
            extra={"duration_seconds": round(time.monotonic() - started_at, 6)},
        )


def initialize_observability(config: ObservabilityConfig) -> ObservabilityRuntime:
    global _runtime
    with _runtime_lock:
        setup_logging(config)
        if _runtime is None or _runtime.config != config:
            provider = None
            if config.tracing_enabled:
                provider = build_tracer_provider(config)
                set_global_tracer_provider(provider)
                instrument_http_clients(provider)
            _runtime = ObservabilityRuntime(
                config=config,
                tracer_provider=provider,
                sentry_enabled=initialize_sentry(config),
                metrics=ApplicationMetrics() if config.metrics_enabled else None,
            )
            set_active_metrics(_runtime.metrics)
        return _runtime
