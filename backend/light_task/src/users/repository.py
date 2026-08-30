from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    def add_user(
        self,
        *,
        email: str,
        username: str,
        hashed_password: str | None,
        email_verified_at: datetime | None = None,
    ) -> User:
        user = User(
            email=email,
            username=username,
            hashed_password=hashed_password,
            email_verified_at=email_verified_at,
        )
        self.session.add(user)
        return user

    def save_user(self, user: User) -> None:
        self.session.add(user)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh_user(self, user: User) -> None:
        await self.session.refresh(user)
