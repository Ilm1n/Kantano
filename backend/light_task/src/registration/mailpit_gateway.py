from __future__ import annotations

from email.message import EmailMessage
from email.utils import formataddr

import aiosmtplib
from aiosmtplib.errors import SMTPRecipientsRefused, SMTPResponseException

from src.config import MailpitConfig
from src.registration.email_gateway import (
    TransientEmailGatewayError,
    build_verification_email_content,
)


class MailpitGateway:
    def __init__(self, config: MailpitConfig) -> None:
        self._config = config

    async def send_verification_email(
        self,
        *,
        recipient: str,
        username: str,
        verification_url: str,
        idempotency_key: str,
    ) -> None:
        content = build_verification_email_content(
            username=username,
            verification_url=verification_url,
        )
        message = EmailMessage()
        message["From"] = formataddr((self._config.from_name, self._config.from_email))
        message["To"] = recipient
        message["Subject"] = content.subject
        message["X-Idempotency-Key"] = idempotency_key
        message.set_content(content.text)
        message.add_alternative(content.html, subtype="html")

        try:
            await aiosmtplib.send(
                message,
                hostname=self._config.host,
                port=self._config.smtp_port,
                timeout=self._config.timeout_seconds,
                use_tls=False,
                start_tls=False,
            )
        except SMTPRecipientsRefused as exc:
            if exc.recipients and all(400 <= refused.code < 500 for refused in exc.recipients):
                raise TransientEmailGatewayError(
                    "SMTP server temporarily refused recipient"
                ) from exc
            raise
        except SMTPResponseException as exc:
            if 400 <= exc.code < 500:
                raise TransientEmailGatewayError(
                    f"SMTP server returned temporary response {exc.code}"
                ) from exc
            raise
        except OSError as exc:
            raise TransientEmailGatewayError("SMTP server is temporarily unavailable") from exc
