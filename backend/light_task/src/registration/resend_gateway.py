# ruff: noqa: RUF001
from __future__ import annotations

from html import escape

import httpx

from src.config import ResendConfig
from src.registration.email_gateway import TransientEmailGatewayError


class ResendGateway:
    def __init__(
        self,
        config: ResendConfig,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport

    async def send_verification_email(
        self,
        *,
        recipient: str,
        username: str,
        verification_url: str,
        idempotency_key: str,
    ) -> None:
        if not self._config.api_key:
            raise RuntimeError("Resend API key is not configured")

        safe_username = escape(username)
        safe_verification_url = escape(verification_url, quote=True)
        payload = {
            "from": f"{self._config.from_name} <{self._config.from_email}>",
            "to": [recipient],
            "subject": "Подтвердите email в Kantano",
            "text": (
                f"Вы начали регистрацию в Kantano с именем пользователя {username}.\n\n"
                f"Подтвердите адрес электронной почты: {verification_url}\n\n"
                "Если вы не создавали аккаунт, просто проигнорируйте это письмо."
            ),
            "html": (
                "<p>Вы начали регистрацию в Kantano с именем пользователя "
                f"<strong>{safe_username}</strong>.</p>"
                "<p>Подтвердите адрес электронной почты:</p>"
                f'<p><a href="{safe_verification_url}">Подтвердить email</a></p>'
                "<p>Если вы не создавали аккаунт, просто проигнорируйте это письмо.</p>"
            ),
        }
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Idempotency-Key": idempotency_key,
            "User-Agent": "Kantano/1.0",
        }

        try:
            async with httpx.AsyncClient(timeout=10, transport=self._transport) as client:
                response = await client.post(
                    f"{self._config.base_url.rstrip('/')}/emails",
                    headers=headers,
                    json=payload,
                )
        except httpx.RequestError as exc:
            raise TransientEmailGatewayError() from exc

        if response.status_code == 429 or response.status_code >= 500:
            raise TransientEmailGatewayError(response.text)
        response.raise_for_status()
