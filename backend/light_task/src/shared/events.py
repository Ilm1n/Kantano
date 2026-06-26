from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    actor_user_id: int | None = None
    project_id: int | None = None
    client_mutation_id: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class DomainEventDispatcher(Protocol):
    async def dispatch(self, events: Sequence[DomainEvent]) -> None:
        pass


class NoopDomainEventDispatcher:
    async def dispatch(self, events: Sequence[DomainEvent]) -> None:
        return None
