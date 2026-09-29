from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import anyio
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from src.config import settings


def checkpointer_dsn() -> str:
    return str(settings.db.url).replace("postgresql+asyncpg://", "postgresql://", 1)


@asynccontextmanager
async def open_checkpointer() -> AsyncIterator[AsyncPostgresSaver]:
    async with AsyncExitStack() as stack:
        saver = await stack.enter_async_context(
            AsyncPostgresSaver.from_conn_string(checkpointer_dsn())
        )
        try:
            yield saver
        finally:
            with anyio.move_on_after(10, shield=True):
                await stack.aclose()


async def setup_checkpointer() -> None:
    async with open_checkpointer() as saver:
        await saver.setup()
