from datetime import datetime

from pydantic import Field, field_validator

from src.constants import HEX_COLOR_PATTERN
from src.projects.constants import ProjectRole
from src.schemas import BaseSchema
from src.users.schemas import UserCollaborator


class ProjectBase(BaseSchema):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    color: str = Field(default="#3B82F6", pattern=HEX_COLOR_PATTERN)

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseSchema):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    color: str | None = Field(None, pattern=HEX_COLOR_PATTERN)

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value


class ProjectRead(ProjectBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime
    current_user_role: ProjectRole | None = None


class ProjectMemberRead(BaseSchema):
    id: int
    user: UserCollaborator
    role: ProjectRole
    joined_at: datetime


class ProjectMemberUpdate(BaseSchema):
    role: ProjectRole
