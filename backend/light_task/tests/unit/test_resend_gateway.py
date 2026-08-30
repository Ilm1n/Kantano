# ruff: noqa: RUF001
import json

import httpx
import pytest

from src.config import ResendConfig
from src.registration.email_gateway import TransientEmailGatewayError
from src.registration.resend_gateway import ResendGateway


@pytest.mark.asyncio
async def test_resend_gateway_sends_verification_request() -> None:
    request_data: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        request_data["url"] = str(request.url)
        request_data["authorization"] = request.headers["Authorization"]
        request_data["idempotency_key"] = request.headers["Idempotency-Key"]
        request_data["user_agent"] = request.headers["User-Agent"]
        request_data["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "email-id"})

    gateway = ResendGateway(
        ResendConfig(api_key="test-key", from_email="no-reply@example.com"),
        httpx.MockTransport(handler),
    )

    await gateway.send_verification_email(
        recipient="user@example.com",
        username='<script>alert("xss")</script>',
        verification_url="https://kantano.ru/verify-email?token=one&source=test",
        idempotency_key="registration-verification-1-token-hash",
    )

    assert request_data["url"] == "https://api.resend.com/emails"
    assert request_data["authorization"] == "Bearer test-key"
    assert request_data["idempotency_key"] == "registration-verification-1-token-hash"
    assert request_data["user_agent"] == "Kantano/1.0"
    assert request_data["payload"] == {
        "from": "Kantano <no-reply@example.com>",
        "to": ["user@example.com"],
        "subject": "Подтвердите email в Kantano",
        "text": (
            'Вы начали регистрацию в Kantano с именем пользователя <script>alert("xss")'
            "</script>.\n\nПодтвердите адрес электронной почты: "
            "https://kantano.ru/verify-email?token=one&source=test\n\n"
            "Если вы не создавали аккаунт, просто проигнорируйте это письмо."
        ),
        "html": (
            "<p>Вы начали регистрацию в Kantano с именем пользователя "
            "<strong>&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;</strong>.</p>"
            "<p>Подтвердите адрес электронной почты:</p>"
            '<p><a href="https://kantano.ru/verify-email?token=one&amp;source=test">'
            "Подтвердить email</a></p>"
            "<p>Если вы не создавали аккаунт, просто проигнорируйте это письмо.</p>"
        ),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [429, 500, 503])
async def test_resend_gateway_treats_temporary_response_as_retryable(
    status_code: int,
) -> None:
    gateway = ResendGateway(
        ResendConfig(api_key="test-key"),
        httpx.MockTransport(lambda _: httpx.Response(status_code)),
    )

    with pytest.raises(TransientEmailGatewayError):
        await gateway.send_verification_email(
            recipient="user@example.com",
            username="example_user",
            verification_url="https://kantano.ru/verify-email?token=test",
            idempotency_key="registration-verification-1-token-hash",
        )


@pytest.mark.asyncio
async def test_resend_gateway_treats_client_error_as_permanent() -> None:
    gateway = ResendGateway(
        ResendConfig(api_key="test-key"),
        httpx.MockTransport(lambda _: httpx.Response(422)),
    )

    with pytest.raises(httpx.HTTPStatusError):
        await gateway.send_verification_email(
            recipient="user@example.com",
            username="example_user",
            verification_url="https://kantano.ru/verify-email?token=test",
            idempotency_key="registration-verification-1-token-hash",
        )


@pytest.mark.asyncio
async def test_resend_gateway_treats_network_error_as_retryable() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    gateway = ResendGateway(
        ResendConfig(api_key="test-key"),
        httpx.MockTransport(fail),
    )

    with pytest.raises(TransientEmailGatewayError):
        await gateway.send_verification_email(
            recipient="user@example.com",
            username="example_user",
            verification_url="https://kantano.ru/verify-email?token=test",
            idempotency_key="registration-verification-1-token-hash",
        )
