from __future__ import annotations

import httpx

from src.config import ResendConfig
from src.registration.email_gateway import (
    TransientEmailGatewayError,
    build_verification_email_content,
)


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

        content = build_verification_email_content(
            username=username,
            verification_url=verification_url,
        )
        payload = {
            "from": f"{self._config.from_name} <{self._config.from_email}>",
            "to": [recipient],
            "subject": content.subject,
            "text": content.text,
            "html": content.html,
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
            # Provider responses may echo email content or verification tokens.
            raise TransientEmailGatewayError(f"Email provider returned HTTP {response.status_code}")
        response.raise_for_status()
