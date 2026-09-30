from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, kw_only=True)
class CreateTagCommand:
    project_id: int
    actor_user_id: int
    name: str
    color: str
    client_mutation_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class ListProjectTagsQuery:
    project_id: int
    actor_user_id: int


@dataclass(frozen=True, kw_only=True)
class UpdateTagCommand:
    tag_id: int
    actor_user_id: int
    changes: dict[str, Any]
    client_mutation_id: str | None = None
    project_id: int | None = None


@dataclass(frozen=True, kw_only=True)
class DeleteTagCommand:
    tag_id: int
    actor_user_id: int
    client_mutation_id: str | None = None
