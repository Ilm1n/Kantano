# ruff: noqa: I001
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select

from src.db.unit_of_work import UnitOfWork
from src.logger import registration_logger
from src.registration.celery_app import celery_app
from src.registration.models import OutboxEvent


MAX_RETRY_DELAY_SECONDS = 300


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


async def _dispatch_outbox_event(event: OutboxEvent) -> None:
    payload = json.loads(event.payload)
    try:
        celery_app.send_task("src.registration.tasks.send_verification_email", kwargs=payload)
    except Exception as exc:
        event.attempts += 1
        event.last_error = type(exc).__name__
        event.next_attempt_at = datetime.now(UTC) + timedelta(
            seconds=min(2**event.attempts, MAX_RETRY_DELAY_SECONDS)
        )
        registration_logger.exception("Outbox event publication failed event_id=%s", event.id)
        return

    event.attempts += 1
    event.last_error = None
    event.next_attempt_at = None
    event.published_at = datetime.now(UTC)
    event.payload = json.dumps({"pending_registration_id": payload["pending_registration_id"]})
    registration_logger.info("Outbox event published event_id=%s", event.id)


async def main() -> None:
    while True:
        try:
            await publish_once()
        except Exception:
            registration_logger.exception("Outbox publisher loop failed")
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
