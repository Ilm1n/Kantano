from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any

from celery import Task

from src.config import settings
from src.db.unit_of_work import UnitOfWork
from src.logger import registration_logger
from src.registration.celery_app import celery_app
from src.registration.email_gateway import TransientEmailGatewayError, build_email_gateway
from src.registration.models import PendingRegistration
from src.registration.use_cases import hash_token

_worker_loop: asyncio.AbstractEventLoop | None = None


def _run_in_worker_loop(coro: Coroutine[Any, Any, None]) -> None:
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
    _worker_loop.run_until_complete(coro)


async def _send(pending_id: int, token: str) -> None:
    async with UnitOfWork() as uow:
        if uow.session is None:
            raise RuntimeError("UnitOfWork has not been entered")
        pending = await uow.session.get(PendingRegistration, pending_id)
        if (
            pending is None
            or pending.expires_at <= datetime.now(UTC)
            or pending.token_hash != hash_token(token)
        ):
            registration_logger.info(
                "Skipped obsolete verification email pending_registration_id=%s",
                pending_id,
            )
            return
        verification_url = f"{settings.frontend.base_url}/verify-email?token={token}"
        gateway = build_email_gateway()
        await gateway.send_verification_email(
            recipient=pending.email,
            username=pending.username,
            verification_url=verification_url,
            idempotency_key=(f"registration-verification-{pending.id}-{hash_token(token)}"),
        )
        pending.email_sent_at = datetime.now(UTC)
        registration_logger.info(
            "Verification email accepted pending_registration_id=%s", pending_id
        )


@celery_app.task(
    bind=True,
    autoretry_for=(TransientEmailGatewayError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def send_verification_email(self: Task, pending_registration_id: int, token: str) -> None:
    try:
        _run_in_worker_loop(_send(pending_registration_id, token))
    except TransientEmailGatewayError:
        registration_logger.warning(
            "Verification email will be retried pending_registration_id=%s",
            pending_registration_id,
        )
        raise
    except Exception:
        registration_logger.exception(
            "Verification email failed permanently pending_registration_id=%s",
            pending_registration_id,
        )
        raise
