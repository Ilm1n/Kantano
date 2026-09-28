from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from src.config import settings


def checkpointer_dsn() -> str:
    return str(settings.db.url).replace("postgresql+asyncpg://", "postgresql://", 1)


@asynccontextmanager
async def open_checkpointer() -> AsyncIterator[AsyncPostgresSaver]:
    async with AsyncPostgresSaver.from_conn_string(checkpointer_dsn()) as saver:
        yield saver


async def setup_checkpointer() -> None:
    async with open_checkpointer() as saver:
        await saver.setup()
