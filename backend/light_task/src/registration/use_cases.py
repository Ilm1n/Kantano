from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError

from src.config import settings
from src.db.unit_of_work import UnitOfWork
from src.errors import ErrorCode
from src.logger import registration_logger
from src.registration.dto import (
    ConfirmRegistrationCommand,
    ResendVerificationCommand,
    StartRegistrationCommand,
    ValidateRegistrationTokenCommand,
)
from src.registration.models import OutboxEvent, PendingRegistration
from src.registration.rate_limiter import RegistrationRateLimiter
from src.registration.repository import RegistrationRepository
from src.shared.errors import (
    AppError,
    DatabaseError,
    ServiceUnavailableError,
    TooManyRequestsError,
)
from src.users.models import User
from src.users.passwords import hash_password


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class StartRegistrationUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        rate_limiter: RegistrationRateLimiter,
    ) -> None:
        self._uow_factory = uow_factory
        self._rate_limiter = rate_limiter

    async def execute(self, command: StartRegistrationCommand) -> None:
        await self._ensure_rate_limit(command.email, command.client_ip)
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = RegistrationRepository(uow.session)
                now = datetime.now(UTC)
                await repository.delete_expired_pending(now)

                if (
                    await repository.get_user_by_email_or_username(
                        email=command.email,
                        username=command.username,
                    )
                    is not None
                ):
                    registration_logger.info("Registration request matched an existing user")
                    return

                pending = await repository.get_pending_by_email_for_update(command.email)
                if pending is not None:
                    registration_logger.info(
                        "Registration request matched an existing pending email"
                    )
                    return

                username_pending = await repository.get_pending_by_username(command.username)
                if username_pending is not None:
                    registration_logger.info(
                        "Registration request matched an existing pending username"
                    )
                    return

                token = secrets.token_urlsafe(32)
                pending = PendingRegistration(
                    email=command.email,
                    username=command.username,
                    token_hash=hash_token(token),
                    expires_at=self._expires_at(now),
                )
                repository.add_pending(pending)
                await repository.flush()

                repository.add_outbox_event(self._verification_event(pending.id, token))
                registration_logger.info(
                    "Created verification request pending_registration_id=%s", pending.id
                )
        except IntegrityError:
            registration_logger.info("Registration collision was handled without disclosure")
        except AppError:
            raise
        except Exception as exc:
            registration_logger.exception("Failed to create pending registration", exc_info=exc)
            raise DatabaseError() from exc

    async def _ensure_rate_limit(self, email: str, client_ip: str) -> None:
        try:
            retry_after = await self._rate_limiter.allow(email=email, client_ip=client_ip)
        except RedisError as exc:
            registration_logger.exception("Registration rate limiter is unavailable", exc_info=exc)
            raise ServiceUnavailableError(ErrorCode.REGISTRATION_RATE_LIMITER_UNAVAILABLE) from exc
        if retry_after is not None:
            registration_logger.warning("Registration rate limit triggered")
            raise TooManyRequestsError(
                ErrorCode.REGISTRATION_RATE_LIMITED,
                retry_after_seconds=retry_after,
            )

    @staticmethod
    def _verification_event(pending_id: int, token: str) -> OutboxEvent:
        return OutboxEvent(
            event_type="verification_email_requested",
            payload=json.dumps({"pending_registration_id": pending_id, "token": token}),
        )

    @staticmethod
    def _expires_at(now: datetime) -> datetime:
        return now + timedelta(hours=settings.registration.verification_ttl_hours)


class ResendVerificationUseCase(StartRegistrationUseCase):
    async def execute(self, command: ResendVerificationCommand) -> None:
        await self._ensure_rate_limit(command.email, command.client_ip)
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = RegistrationRepository(uow.session)
                now = datetime.now(UTC)
                await repository.delete_expired_pending(now)
                pending = await repository.get_pending_by_email_for_update(command.email)
                if pending is None:
                    return

                token = secrets.token_urlsafe(32)
                pending.token_hash = hash_token(token)
                pending.expires_at = self._expires_at(now)
                pending.email_sent_at = None
                repository.add_outbox_event(self._verification_event(pending.id, token))
                registration_logger.info(
                    "Resent verification request pending_registration_id=%s", pending.id
                )
        except AppError:
            raise
        except Exception as exc:
            registration_logger.exception("Failed to resend verification email", exc_info=exc)
            raise DatabaseError() from exc


class ConfirmRegistrationUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: ConfirmRegistrationCommand) -> bool:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = RegistrationRepository(uow.session)
                pending = await repository.get_pending_by_token_hash_for_update(
                    hash_token(command.token)
                )
                if pending is None:
                    return False
                if pending.expires_at <= datetime.now(UTC):
                    await repository.delete_pending(pending)
                    return False
                if await repository.get_user_by_email_or_username(
                    email=pending.email,
                    username=pending.username,
                ):
                    await repository.delete_pending(pending)
                    return False

                repository.add_user(
                    User(
                        email=pending.email,
                        username=pending.username,
                        hashed_password=hash_password(command.password),
                        email_verified_at=datetime.now(UTC),
                    )
                )
                await repository.delete_pending(pending)
                registration_logger.info("Confirmed registration")
                return True
        except IntegrityError:
            registration_logger.info("Registration confirmation lost a concurrent race")
            return False
        except Exception as exc:
            registration_logger.exception("Failed to confirm registration", exc_info=exc)
            raise DatabaseError() from exc


class ValidateRegistrationTokenUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: ValidateRegistrationTokenCommand) -> bool:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = RegistrationRepository(uow.session)
                pending = await repository.get_pending_by_token_hash(hash_token(command.token))
                return pending is not None and pending.expires_at > datetime.now(UTC)
        except Exception as exc:
            registration_logger.exception("Failed to validate registration token", exc_info=exc)
            raise DatabaseError() from exc
