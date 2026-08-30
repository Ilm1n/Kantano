from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.registration.celery_app import EMAIL_VERIFICATION_QUEUE, celery_app
from src.registration.models import OutboxEvent, PendingRegistration
from src.registration.outbox_publisher import publish_once
from src.registration.tasks import _send
from src.registration.use_cases import hash_token


async def _create_event() -> int:
    from src.db.unit_of_work import UnitOfWork

    async with UnitOfWork() as uow:
        if uow.session is None:
            raise RuntimeError("UnitOfWork has not been entered")
        event = OutboxEvent(
            event_type="verification_email_requested",
            payload=json.dumps({"pending_registration_id": 7, "token": "test-token"}),
        )
        uow.session.add(event)
        await uow.session.flush()
        return event.id


async def _get_event(event_id: int) -> OutboxEvent:
    from src.db.database import db_helper

    async with db_helper.async_session_maker() as session:
        event = await session.scalar(select(OutboxEvent).where(OutboxEvent.id == event_id))
        assert event is not None
        return event


@pytest.mark.asyncio
async def test_outbox_event_survives_broker_failure_and_retries(monkeypatch) -> None:
    event_id = await _create_event()

    def fail_publish(*args, **kwargs) -> None:
        raise ConnectionError("broker unavailable")

    monkeypatch.setattr(celery_app, "send_task", fail_publish)
    await publish_once()

    failed_event = await _get_event(event_id)
    assert failed_event.published_at is None
    assert failed_event.attempts == 1
    assert failed_event.last_error == "ConnectionError"
    assert failed_event.next_attempt_at is not None

    def publish(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(celery_app, "send_task", publish)

    async def make_due() -> None:
        from src.db.unit_of_work import UnitOfWork

        async with UnitOfWork() as uow:
            if uow.session is None:
                raise RuntimeError("UnitOfWork has not been entered")
            stored = await uow.session.get(OutboxEvent, event_id)
            assert stored is not None
            stored.next_attempt_at = None

    await make_due()
    await publish_once()

    published_event = await _get_event(event_id)
    assert published_event.published_at is not None
    assert published_event.attempts == 2
    assert published_event.last_error is None
    assert json.loads(published_event.payload) == {"pending_registration_id": 7}


@pytest.mark.asyncio
async def test_outbox_event_is_published_to_rabbitmq() -> None:
    with celery_app.connection_for_read() as connection:
        queue = celery_app.amqp.queues[EMAIL_VERIFICATION_QUEUE](connection)
        queue.declare()
        queue.purge()

    event_id = await _create_event()

    await publish_once()

    published_event = await _get_event(event_id)
    assert published_event.published_at is not None
    assert published_event.attempts == 1
    assert json.loads(published_event.payload) == {"pending_registration_id": 7}

    with celery_app.connection_for_read() as connection:
        queue = celery_app.amqp.queues[EMAIL_VERIFICATION_QUEUE](connection)
        message = queue.get(no_ack=False)
        assert message is not None
        _, kwargs, _ = message.payload
        assert kwargs == {
            "pending_registration_id": 7,
            "token": "test-token",
        }
        message.ack()


def test_celery_uses_persistent_confirmed_email_queue() -> None:
    assert "src.registration.tasks.send_verification_email" in celery_app.tasks
    assert celery_app.conf.broker_transport_options["confirm_publish"] is True
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_default_delivery_mode == "persistent"
    assert celery_app.conf.task_default_queue == "email_verification"
    assert celery_app.conf.task_queues[0].queue_arguments == {"x-queue-type": "quorum"}
    assert celery_app.conf.task_queues[0].exchange.type == "topic"
    assert celery_app.conf.broker_native_delayed_delivery_queue_type == "classic"
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert celery_app.conf.worker_enable_remote_control is False
    assert celery_app.conf.worker_send_task_events is False
    assert celery_app.conf.worker_detect_quorum_queues is True


@pytest.mark.asyncio
async def test_worker_uses_stable_idempotency_key_and_skips_obsolete_delivery(
    monkeypatch,
) -> None:
    from src.db.unit_of_work import UnitOfWork

    async with UnitOfWork() as uow:
        assert uow.session is not None
        pending = PendingRegistration(
            email="worker@example.com",
            username="worker_user",
            token_hash=hash_token("current-token"),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        uow.session.add(pending)
        await uow.session.flush()
        pending_id = pending.id

    sent: list[tuple[str, str, str]] = []

    class FakeGateway:
        async def send_verification_email(
            self,
            *,
            recipient: str,
            username: str,
            verification_url: str,
            idempotency_key: str,
        ) -> None:
            sent.append((recipient, verification_url, idempotency_key))

    monkeypatch.setattr("src.registration.tasks.build_email_gateway", lambda: FakeGateway())

    await _send(pending_id, "current-token")
    await _send(pending_id, "current-token")
    await _send(pending_id, "old-token")

    assert len(sent) == 2
    assert sent[0][0] == "worker@example.com"
    assert sent[0][2] == sent[1][2]

    async with UnitOfWork() as uow:
        assert uow.session is not None
        stored = await uow.session.get(PendingRegistration, pending_id)
        assert stored is not None
        stored.token_hash = hash_token("new-token")

    await _send(pending_id, "new-token")

    assert len(sent) == 3
    assert sent[2][2] != sent[0][2]
