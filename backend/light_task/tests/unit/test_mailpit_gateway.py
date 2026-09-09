from email.message import EmailMessage
from typing import Any

import aiosmtplib
import pytest
from aiosmtplib.errors import SMTPDataError, SMTPException, SMTPTimeoutError

from src.config import MailpitConfig
from src.registration.email_gateway import TransientEmailGatewayError
from src.registration.mailpit_gateway import MailpitGateway


@pytest.mark.asyncio
async def test_mailpit_gateway_sends_multipart_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: dict[str, Any] = {}

    async def fake_send(message: EmailMessage, **kwargs: object) -> tuple[dict[str, object], str]:
        sent["message"] = message
        sent["kwargs"] = kwargs
        return {}, "accepted"

    monkeypatch.setattr(aiosmtplib, "send", fake_send)
    gateway = MailpitGateway(
        MailpitConfig(
            host="mailpit",
            smtp_port=1025,
            timeout_seconds=5,
            from_email="no-reply@kantano.local",
            from_name="Kantano",
        )
    )

    await gateway.send_verification_email(
        recipient="user@example.com",
        username='<script>alert("xss")</script>',
        verification_url="http://localhost:5173/verify-email?token=one&source=test",
        idempotency_key="registration-verification-1-token-hash",
    )

    message = sent["message"]
    assert isinstance(message, EmailMessage)
    assert message["From"] == "Kantano <no-reply@kantano.local>"
    assert message["To"] == "user@example.com"
    assert message["Subject"] == "Подтвердите email в Kantano"
    assert message["X-Idempotency-Key"] == "registration-verification-1-token-hash"
    assert message.get_body(preferencelist=("plain",)) is not None
    assert (
        '<script>alert("xss")</script>' in message.get_body(preferencelist=("plain",)).get_content()
    )
    assert message.get_body(preferencelist=("html",)) is not None
    assert "&lt;script&gt;" in message.get_body(preferencelist=("html",)).get_content()
    assert sent["kwargs"] == {
        "hostname": "mailpit",
        "port": 1025,
        "timeout": 5.0,
        "use_tls": False,
        "start_tls": False,
    }


async def _send_with_error(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    async def fail(*_: object, **__: object) -> tuple[dict[str, object], str]:
        raise error

    monkeypatch.setattr(aiosmtplib, "send", fail)
    await MailpitGateway(MailpitConfig()).send_verification_email(
        recipient="user@example.com",
        username="example_user",
        verification_url="http://localhost:5173/verify-email?token=test",
        idempotency_key="registration-verification-1-token-hash",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ConnectionRefusedError(), SMTPTimeoutError("timed out")])
async def test_mailpit_gateway_treats_network_errors_as_retryable(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    with pytest.raises(TransientEmailGatewayError):
        await _send_with_error(monkeypatch, error)


@pytest.mark.asyncio
async def test_mailpit_gateway_treats_smtp_4xx_as_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(TransientEmailGatewayError):
        await _send_with_error(monkeypatch, SMTPDataError(451, "try later"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [SMTPDataError(550, "rejected"), SMTPException("invalid message")],
)
async def test_mailpit_gateway_does_not_retry_permanent_smtp_errors(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    with pytest.raises(type(error)):
        await _send_with_error(monkeypatch, error)
