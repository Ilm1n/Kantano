# ruff: noqa: I001
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from opentelemetry.context import Context

from src.db.database import db_helper
from src.db.unit_of_work import UnitOfWork
from src.logger import registration_logger
from src.observability.context import contextualize
from src.observability.propagation import extract_outbox_context
from src.observability.sentry import capture_exception_once
from src.observability.tracing import get_tracer, mark_current_span_error
from src.registration.celery_app import celery_app, observability
from src.registration.models import OutboxEvent


MAX_RETRY_DELAY_SECONDS = 300
tracer = get_tracer(__name__)


async def publish_once() -> None:
    async with UnitOfWork() as uow:
        if uow.session is None:
            raise RuntimeError("UnitOfWork has not been entered")
        now = datetime.now(UTC)
        events = (
            await uow.session.scalars(
                select(OutboxEvent)
                .where(
                    OutboxEvent.published_at.is_(None),
                    or_(
                        OutboxEvent.next_attempt_at.is_(None),
                        OutboxEvent.next_attempt_at <= now,
                    ),
                )
                .with_for_update(skip_locked=True)
                .limit(20)
            )
        ).all()
        for event in events:
            await _dispatch_outbox_event(event)
    if observability.metrics is not None:
        observability.metrics.record_publisher_poll()


async def update_outbox_stats() -> None:
    async with db_helper.async_session_maker() as session:
        count, oldest = (
            await session.execute(
                select(func.count(OutboxEvent.id), func.min(OutboxEvent.created_at)).where(
                    OutboxEvent.published_at.is_(None)
                )
            )
        ).one()
    if observability.metrics is not None:
        observability.metrics.update_outbox_stats(
            count=int(count),
            oldest_timestamp=oldest.timestamp() if oldest is not None else None,
        )


async def _dispatch_outbox_event(event: OutboxEvent) -> None:
    payload = json.loads(event.payload)
    extracted = extract_outbox_context(event.trace_context)
    if not extracted.valid:
        registration_logger.warning(
            "Invalid outbox trace context; starting a new trace",
            extra={"outbox_event_id": event.id},
        )
    with contextualize(
        request_id=extracted.request_id,
        outbox_event_id=event.id,
        attempt=event.attempts + 1,
    ):
        with tracer.start_as_current_span(
            "registration.outbox.publish",
            # NULL/invalid legacy context must start a genuinely new trace even
            # if this coroutine ever acquires an ambient instrumentation context.
            context=extracted.context or Context(),
            attributes={
                "messaging.system": "rabbitmq",
                "messaging.operation.name": "publish",
                "outbox.event_id": event.id,
                "outbox.event_type": event.event_type,
            },
        ):
            try:
                celery_app.send_task(
                    "src.registration.tasks.send_verification_email",
                    kwargs=payload,
                    headers={
                        "request_id": extracted.request_id,
                        "outbox_event_id": str(event.id),
                    },
                )
            except Exception as exc:
                mark_current_span_error(exc)
                event.attempts += 1
                event.last_error = type(exc).__name__
                event.next_attempt_at = datetime.now(UTC) + timedelta(
                    seconds=min(2**event.attempts, MAX_RETRY_DELAY_SECONDS)
                )
                if observability.metrics is not None:
                    observability.metrics.record_outbox_publish("failure")
                registration_logger.exception(
                    "Outbox event publication failed",
                    extra={"outbox_event_id": event.id},
                )
                return

            event.attempts += 1
            event.last_error = None
            event.next_attempt_at = None
            event.published_at = datetime.now(UTC)
            event.payload = json.dumps(
                {"pending_registration_id": payload["pending_registration_id"]}
            )
            if observability.metrics is not None:
                observability.metrics.record_outbox_publish("success")
            registration_logger.info(
                "Outbox event published",
                extra={"outbox_event_id": event.id},
            )


async def main() -> None:
    registration_logger.info("Outbox publisher started")
    next_stats_update = 0.0
    try:
        while True:
            try:
                await publish_once()
                now = asyncio.get_running_loop().time()
                if now >= next_stats_update:
                    await update_outbox_stats()
                    next_stats_update = now + 30
            except Exception as exc:
                capture_exception_once(exc)
                registration_logger.exception("Outbox publisher loop failed")
            await asyncio.sleep(2)
    finally:
        registration_logger.info("Outbox publisher stopped")
        await db_helper.dispose()
        observability.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
