from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.registration.models import OutboxEvent, PendingRegistration
from src.users.models import User


class RegistrationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def delete_expired_pending(self, now: datetime) -> None:
        await self._session.execute(
            delete(PendingRegistration).where(PendingRegistration.expires_at <= now)
        )

    async def get_user_by_email_or_username(self, *, email: str, username: str) -> User | None:
        result = await self._session.execute(
            select(User).where(or_(User.email == email, User.username == username))
        )
        return result.scalars().first()

    async def get_pending_by_email_for_update(self, email: str) -> PendingRegistration | None:
        result = await self._session.execute(
            select(PendingRegistration).where(PendingRegistration.email == email).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_pending_by_username(self, username: str) -> PendingRegistration | None:
        result = await self._session.execute(
            select(PendingRegistration).where(PendingRegistration.username == username)
        )
        return result.scalar_one_or_none()

    async def get_pending_by_token_hash_for_update(
        self,
        token_hash: str,
    ) -> PendingRegistration | None:
        result = await self._session.execute(
            select(PendingRegistration)
            .where(PendingRegistration.token_hash == token_hash)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_pending_by_token_hash(self, token_hash: str) -> PendingRegistration | None:
        result = await self._session.execute(
            select(PendingRegistration).where(PendingRegistration.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    def add_pending(self, pending: PendingRegistration) -> None:
        self._session.add(pending)

    def add_outbox_event(self, event: OutboxEvent) -> None:
        self._session.add(event)

    def add_user(self, user: User) -> None:
        self._session.add(user)

    async def delete_pending(self, pending: PendingRegistration) -> None:
        await self._session.delete(pending)

    async def flush(self) -> None:
        await self._session.flush()
