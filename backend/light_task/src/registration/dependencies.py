from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

import redis.asyncio as redis
from fastapi import Depends

from src.config import settings
from src.db.unit_of_work import UnitOfWork
from src.registration.rate_limiter import RegistrationRateLimiter
from src.registration.use_cases import (
    ConfirmRegistrationUseCase,
    ResendVerificationUseCase,
    StartRegistrationUseCase,
    ValidateRegistrationTokenUseCase,
)


async def get_registration_rate_limiter() -> AsyncGenerator[RegistrationRateLimiter, None]:
    client = redis.from_url(settings.realtime.redis_url, encoding="utf-8", decode_responses=True)
    try:
        yield RegistrationRateLimiter(client, settings.registration)
    finally:
        await client.aclose()


def get_start_registration_use_case(
    rate_limiter: Annotated[RegistrationRateLimiter, Depends(get_registration_rate_limiter)],
) -> StartRegistrationUseCase:
    return StartRegistrationUseCase(lambda: UnitOfWork(), rate_limiter)


def get_resend_verification_use_case(
    rate_limiter: Annotated[RegistrationRateLimiter, Depends(get_registration_rate_limiter)],
) -> ResendVerificationUseCase:
    return ResendVerificationUseCase(lambda: UnitOfWork(), rate_limiter)


def get_confirm_registration_use_case() -> ConfirmRegistrationUseCase:
    return ConfirmRegistrationUseCase(lambda: UnitOfWork())


def get_validate_registration_token_use_case() -> ValidateRegistrationTokenUseCase:
    return ValidateRegistrationTokenUseCase(lambda: UnitOfWork())
