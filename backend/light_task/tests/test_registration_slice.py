from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from src.db.database import db_helper
from src.registration.models import OutboxEvent, PendingRegistration
from src.users.models import User

PASSWORD = "VeryStrongPass123!"


async def _pending_for_email(email: str) -> PendingRegistration | None:
    async with db_helper.async_session_maker() as session:
        return await session.scalar(
            select(PendingRegistration).where(PendingRegistration.email == email)
        )


async def _outbox_events() -> list[OutboxEvent]:
    async with db_helper.async_session_maker() as session:
        return list((await session.scalars(select(OutboxEvent).order_by(OutboxEvent.id))).all())


async def _user_for_email(email: str) -> User | None:
    async with db_helper.async_session_maker() as session:
        return await session.scalar(select(User).where(User.email == email))


def test_registration_creates_pending_and_outbox_but_not_user(client: TestClient) -> None:
    email = "pending@example.com"
    response = client.post(
        "/api/registration",
        json={"username": "pending_user", "email": email},
    )

    assert response.status_code == 202
    assert response.json() == {"detail": "CHECK_YOUR_EMAIL"}
    pending = asyncio.run(_pending_for_email(email))
    assert pending is not None
    assert pending.token_hash
    assert asyncio.run(_user_for_email(email)) is None
    events = asyncio.run(_outbox_events())
    assert len(events) == 1
    assert events[0].event_type == "verification_email_requested"


def test_confirmation_creates_verified_user_and_token_is_single_use(client: TestClient) -> None:
    email = "confirmed@example.com"
    client.post(
        "/api/registration",
        json={"username": "confirmed_user", "email": email},
    )
    event = asyncio.run(_outbox_events())[0]
    token = str(json.loads(event.payload)["token"])

    validation = client.post("/api/registration/validate", json={"token": token})
    assert validation.status_code == 204

    response = client.post("/api/registration/confirm", json={"token": token, "password": PASSWORD})
    assert response.status_code == 200
    assert response.json() == {"detail": "EMAIL_CONFIRMED"}
    user = asyncio.run(_user_for_email(email))
    assert user is not None
    assert user.email_verified_at is not None
    assert asyncio.run(_pending_for_email(email)) is None

    repeated = client.post("/api/registration/confirm", json={"token": token, "password": PASSWORD})
    assert repeated.status_code == 400
    assert repeated.json()["error"]["code"] == "INVALID_OR_EXPIRED_VERIFICATION_TOKEN"

    repeated_validation = client.post("/api/registration/validate", json={"token": token})
    assert repeated_validation.status_code == 400
    assert repeated_validation.json()["error"]["code"] == "INVALID_OR_EXPIRED_VERIFICATION_TOKEN"


def test_login_is_impossible_until_confirmation(client: TestClient) -> None:
    client.post(
        "/api/registration",
        json={"username": "no_login", "email": "no-login@example.com"},
    )

    response = client.post(
        "/api/auth/login",
        data={"username": "no_login", "password": PASSWORD},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_legacy_register_endpoint_is_removed(client: TestClient) -> None:
    response = client.post(
        "/api/users/register",
        json={"username": "legacy", "email": "legacy@example.com", "password": PASSWORD},
    )

    assert response.status_code == 405


def test_resend_invalidates_previous_token(client: TestClient) -> None:
    email = "resend@example.com"
    client.post(
        "/api/registration",
        json={"username": "resend_user", "email": email},
    )
    first_token = str(json.loads(asyncio.run(_outbox_events())[0].payload)["token"])

    redis_key = "registration:cooldown:" + __import__("hashlib").sha256(email.encode()).hexdigest()
    asyncio.run(_delete_redis_key(redis_key))
    resend = client.post("/api/registration/resend", json={"email": email})
    assert resend.status_code == 202
    second_token = str(json.loads(asyncio.run(_outbox_events())[1].payload)["token"])

    expired = client.post(
        "/api/registration/confirm", json={"token": first_token, "password": PASSWORD}
    )
    assert expired.status_code == 400
    confirmed = client.post(
        "/api/registration/confirm", json={"token": second_token, "password": PASSWORD}
    )
    assert confirmed.status_code == 200


def test_repeated_registration_cannot_replace_pending_identity_or_token(client: TestClient) -> None:
    email = "protected-pending@example.com"
    client.post(
        "/api/registration",
        json={"username": "original_user", "email": email},
    )
    initial_pending = asyncio.run(_pending_for_email(email))
    assert initial_pending is not None

    redis_key = "registration:cooldown:" + __import__("hashlib").sha256(email.encode()).hexdigest()
    asyncio.run(_delete_redis_key(redis_key))
    repeated = client.post(
        "/api/registration",
        json={"username": "attacker_user", "email": email},
    )

    assert repeated.status_code == 202
    pending = asyncio.run(_pending_for_email(email))
    assert pending is not None
    assert pending.username == "original_user"
    assert pending.token_hash == initial_pending.token_hash
    assert len(asyncio.run(_outbox_events())) == 1


def test_resend_rate_limit_returns_retry_after(client: TestClient) -> None:
    email = "limited@example.com"
    client.post(
        "/api/registration",
        json={"username": "limited_user", "email": email},
    )

    response = client.post("/api/registration/resend", json={"email": email})

    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"
    assert response.json()["error"]["code"] == "REGISTRATION_RATE_LIMITED"


async def _delete_redis_key(key: str) -> None:
    import redis.asyncio as redis

    from src.config import settings

    client = redis.from_url(settings.realtime.redis_url)
    try:
        await client.delete(key)
    finally:
        await client.aclose()


def test_expired_registration_is_ignored(client: TestClient) -> None:
    email = "expired@example.com"
    client.post(
        "/api/registration",
        json={"username": "expired_name", "email": email},
    )

    async def expire_pending() -> None:
        async with db_helper.async_session_maker() as session:
            pending = await session.scalar(
                select(PendingRegistration).where(PendingRegistration.email == email)
            )
            assert pending is not None
            pending.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(expire_pending())
    response = client.post(
        "/api/registration",
        json={"username": "expired_name", "email": "fresh@example.com"},
    )
    assert response.status_code == 202
    assert asyncio.run(_pending_for_email("fresh@example.com")) is not None
