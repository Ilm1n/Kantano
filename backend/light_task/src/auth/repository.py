from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models import User


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user_by_username_or_email(self, username_or_email: str) -> User | None:
        stmt = select(User).where(
            or_(User.username == username_or_email, User.email == username_or_email)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_user(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_user_by_yandex_id(self, yandex_id: str) -> User | None:
        result = await self.session.execute(select(User).where(User.yandex_id == yandex_id))
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def username_exists(self, username: str) -> bool:
        result = await self.session.execute(select(User.id).where(User.username == username))
        return result.scalar_one_or_none() is not None

    def add_yandex_user(
        self,
        *,
        email: str,
        username: str,
        full_name: str | None,
        yandex_id: str,
    ) -> User:
        user = User(
            email=email,
            username=username,
            full_name=full_name,
            hashed_password=None,
            yandex_id=yandex_id,
        )
        self.session.add(user)
        return user

    def save_user(self, user: User) -> None:
        self.session.add(user)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh_user(self, user: User) -> None:
        await self.session.refresh(user)
