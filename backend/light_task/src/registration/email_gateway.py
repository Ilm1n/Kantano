from __future__ import annotations

from typing import Protocol

from src.config import settings


class TransientEmailGatewayError(Exception):
    """The provider may accept the request after a retry."""


class EmailGateway(Protocol):
    async def send_verification_email(
        self,
        *,
        recipient: str,
        username: str,
        verification_url: str,
        idempotency_key: str,
    ) -> None: ...


def build_email_gateway() -> EmailGateway:
    if settings.email.provider == "resend":
        from src.registration.resend_gateway import ResendGateway

        return ResendGateway(settings.resend)
    raise RuntimeError(f"Unsupported email provider: {settings.email.provider}")
