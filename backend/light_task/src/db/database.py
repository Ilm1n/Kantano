import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from src.config import settings


class DatabaseHelper:
    def __init__(
        self,
        url: str,
        echo: bool = False,
        echo_pool: bool = False,
        pool_size: int = 5,
        max_overflow: int = 10,
    ):
        engine_kwargs = {
            "url": url,
            "echo": echo,
            "echo_pool": echo_pool,
            "pool_size": pool_size,
            "max_overflow": max_overflow,
        }
        if os.getenv("LIGHTTASK_TESTING") == "1":
            engine_kwargs["poolclass"] = NullPool
            engine_kwargs.pop("pool_size", None)
            engine_kwargs.pop("max_overflow", None)

        self.engine: AsyncEngine = create_async_engine(
            **engine_kwargs,
        )
        self.async_session_maker = async_sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )

    async def dispose(self):
        await self.engine.dispose()

    async def get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.async_session_maker() as session:
            yield session


db_helper = DatabaseHelper(
    url=str(settings.db.url),
    echo=settings.db.echo,
    echo_pool=settings.db.echo_pool,
    pool_size=settings.db.pool_size,
    max_overflow=settings.db.max_overflow,
)
