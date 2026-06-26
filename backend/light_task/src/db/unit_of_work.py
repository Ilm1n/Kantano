from __future__ import annotations

from collections.abc import Callable, Sequence
from types import TracebackType
from typing import Literal, Self

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import db_helper
from src.shared.events import (
    DomainEvent,
    DomainEventDispatcher,
    NoopDomainEventDispatcher,
)


class UnitOfWork:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession] | None = None,
        event_dispatcher: DomainEventDispatcher | None = None,
    ) -> None:
        self._session_factory = session_factory or db_helper.async_session_maker
        self._event_dispatcher = event_dispatcher or NoopDomainEventDispatcher()
        self._events: list[DomainEvent] = []
        self._committed = False
        self.session: AsyncSession | None = None

    async def __aenter__(self) -> Self:
        self.session = self._session_factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        try:
            if exc_type is not None:
                await self.rollback()
                return False

            if not self._committed:
                await self.commit()
        finally:
            await self.close()

        return False

    def collect_event(self, event: DomainEvent) -> None:
        self._events.append(event)

    def collect_events(self, events: Sequence[DomainEvent]) -> None:
        self._events.extend(events)

    async def commit(self) -> None:
        if self.session is None:
            raise RuntimeError("UnitOfWork has not been entered")

        try:
            await self.session.commit()
        except Exception:
            await self.rollback()
            raise

        self._committed = True

        events = tuple(self._events)
        self._events.clear()
        if events:
            await self._event_dispatcher.dispatch(events)

    async def rollback(self) -> None:
        if self.session is None:
            return

        await self.session.rollback()
        self._events.clear()

    async def close(self) -> None:
        if self.session is None:
            return

        await self.session.close()
        self.session = None
