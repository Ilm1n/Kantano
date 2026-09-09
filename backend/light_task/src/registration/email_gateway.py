# ruff: noqa: RUF001
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Protocol

from src.config import settings


class TransientEmailGatewayError(Exception):
    """The provider may accept the request after a retry."""


@dataclass(frozen=True, slots=True)
class VerificationEmailContent:
    subject: str
    text: str
    html: str


def build_verification_email_content(
    *, username: str, verification_url: str
) -> VerificationEmailContent:
    safe_username = escape(username)
    safe_verification_url = escape(verification_url, quote=True)
    return VerificationEmailContent(
        subject="Подтвердите email в Kantano",
        text=(
            f"Вы начали регистрацию в Kantano с именем пользователя {username}.\n\n"
            f"Подтвердите адрес электронной почты: {verification_url}\n\n"
            "Если вы не создавали аккаунт, просто проигнорируйте это письмо."
        ),
        html=(
            "<p>Вы начали регистрацию в Kantano с именем пользователя "
            f"<strong>{safe_username}</strong>.</p>"
            "<p>Подтвердите адрес электронной почты:</p>"
            f'<p><a href="{safe_verification_url}">Подтвердить email</a></p>'
            "<p>Если вы не создавали аккаунт, просто проигнорируйте это письмо.</p>"
        ),
    )


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
    if settings.email.provider == "mailpit":
        from src.registration.mailpit_gateway import MailpitGateway

        return MailpitGateway(settings.mailpit)
    raise RuntimeError(f"Unsupported email provider: {settings.email.provider}")
