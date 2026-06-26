from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import Field

from src.schemas import BaseSchema

SCHEMA_VERSION = 1
SYSTEM_ACTOR_USER_ID = 0


class RealtimeScope(StrEnum):
    USER = "user"
    PROJECT = "project"


class RealtimeAudience(StrEnum):
    ALL = "all"
    MANAGER = "manager"


class RealtimeEventType(StrEnum):
    PROJECT_ADDED_TO_USER = "project.added_to_user"
    PROJECT_REMOVED_FROM_USER = "project.removed_from_user"
    PROJECT_LIST_ITEM_UPDATED = "project.list_item_updated"

    PROJECT_UPDATED = "project.updated"
    PROJECT_DELETED = "project.deleted"
    MEMBER_ADDED = "member.added"
    MEMBER_ROLE_CHANGED = "member.role_changed"
    MEMBER_REMOVED = "member.removed"
    TAG_CREATED = "tag.created"
    TAG_UPDATED = "tag.updated"
    TAG_DELETED = "tag.deleted"
    COLUMN_CREATED = "column.created"
    COLUMN_UPDATED = "column.updated"
    COLUMN_DELETED = "column.deleted"
    COLUMNS_REORDERED = "columns.reordered"
    TASK_CREATED = "task.created"
    TASK_UPDATED = "task.updated"
    TASK_DELETED = "task.deleted"
    TASK_MOVED = "task.moved"

    INVITATION_CREATED = "invitation.created"
    INVITATION_DELETED = "invitation.deleted"

    TASK_VIEWING_STARTED = "task.viewing.started"
    TASK_VIEWING_STOPPED = "task.viewing.stopped"
    TASK_EDITING_STARTED = "task.editing.started"
    TASK_EDITING_STOPPED = "task.editing.stopped"
    TASK_PRESENCE_SYNC = "task.presence.sync"

    PROJECT_PRESENCE_SYNC = "project.presence.sync"
    PROJECT_PRESENCE_CHANGED = "project.presence.changed"


class RealtimeEventEnvelope(BaseSchema):
    schema_version: int = SCHEMA_VERSION
    event_id: str
    event_type: str
    scope: RealtimeScope
    project_id: int | None = None
    actor_user_id: int
    occurred_at: datetime
    payload: dict[str, Any]
    client_mutation_id: str | None = None


class RealtimeDeliveryMessage(BaseSchema):
    envelope: RealtimeEventEnvelope
    user_ids: list[int] = Field(default_factory=list)
    project_id: int | None = None
    audience: RealtimeAudience = RealtimeAudience.ALL
    exclude_user_ids: list[int] = Field(default_factory=list)


def new_event_envelope(
    *,
    event_type: str | RealtimeEventType,
    scope: RealtimeScope,
    actor_user_id: int,
    payload: dict[str, Any],
    project_id: int | None = None,
    client_mutation_id: str | None = None,
) -> RealtimeEventEnvelope:
    return RealtimeEventEnvelope(
        schema_version=SCHEMA_VERSION,
        event_id=str(uuid4()),
        event_type=str(event_type),
        scope=scope,
        project_id=project_id,
        actor_user_id=actor_user_id,
        occurred_at=datetime.now(UTC),
        payload=payload,
        client_mutation_id=client_mutation_id,
    )
