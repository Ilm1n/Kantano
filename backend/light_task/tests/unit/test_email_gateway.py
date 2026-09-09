import pytest
from pydantic import ValidationError

from src.config import Settings, settings
from src.registration.email_gateway import (
    build_email_gateway,
    build_verification_email_content,
)
from src.registration.mailpit_gateway import MailpitGateway
from src.registration.resend_gateway import ResendGateway


@pytest.mark.parametrize(
    ("provider", "gateway_type"),
    [("resend", ResendGateway), ("mailpit", MailpitGateway)],
)
def test_build_email_gateway_selects_configured_provider(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    gateway_type: type[ResendGateway] | type[MailpitGateway],
) -> None:
    monkeypatch.setattr(settings.email, "provider", provider)

    assert isinstance(build_email_gateway(), gateway_type)


def test_verification_email_content_escapes_html_only() -> None:
    content = build_verification_email_content(
        username='<script>alert("xss")</script>',
        verification_url="https://kantano.ru/verify-email?token=one&source=test",
    )

    assert content.subject == "Подтвердите email в Kantano"
    assert '<script>alert("xss")</script>' in content.text
    assert "token=one&source=test" in content.text
    assert "&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;" in content.html
    assert "token=one&amp;source=test" in content.html


def test_settings_reject_mailpit_in_production() -> None:
    with pytest.raises(ValidationError, match="Mailpit email provider is not allowed"):
        Settings(
            _env_file=None,
            db={"user": "test", "password": "test", "name": "test"},
            s3={"backend": "local"},
            email={"provider": "mailpit"},
            observability={
                "environment": "production",
                "tracing_enabled": True,
                "metrics_enabled": True,
                "log_format": "json",
                "sentry_dsn": "https://example.invalid/1",
            },
        )
