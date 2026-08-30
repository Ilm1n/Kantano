from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from src.db.database import db_helper
from src.users.models import User
from src.users.passwords import hash_password


async def _create_verified_user(*, username: str, email: str, password: str) -> None:
    async with db_helper.async_session_maker() as session:
        session.add(
            User(
                username=username,
                email=email,
                hashed_password=hash_password(password),
                email_verified_at=datetime.now(UTC),
            )
        )
        await session.commit()


def register_and_confirm(
    client: TestClient,
    *,
    username: str,
    email: str,
    password: str,
) -> None:
    del client
    asyncio.run(_create_verified_user(username=username, email=email, password=password))
