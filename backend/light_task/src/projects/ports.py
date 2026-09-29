from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession


class ProjectDeletionHook(Protocol):
    async def prepare(self, session: AsyncSession, project_id: int) -> None: ...

    async def cleanup(self) -> None: ...
