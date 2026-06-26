from datetime import datetime
from typing import Any

from pydantic import EmailStr, Field, computed_field

from src.config import settings
from src.errors import SuccessCode
from src.projects.constants import ProjectRole
from src.schemas import BaseSchema


class InvitationCreate(BaseSchema):
    role: ProjectRole = ProjectRole.MEMBER
    email: EmailStr | None = None
    max_uses: int | None = Field(
        1, ge=1, description="Сколько раз можно использовать ссылку. None = безлимит."
    )
    expires_in_days: int = Field(7, ge=1, le=30, description="Срок действия в днях")


class InvitationRead(BaseSchema):
    id: int
    token: str
    role: ProjectRole
    email: str | None
    max_uses: int | None
    used_count: int
    expires_at: datetime

    @computed_field
    def link(self) -> str:
        return f"{settings.invite.base_url}/{self.token}"


class SuccessPayload(BaseSchema):
    code: SuccessCode
    params: dict[str, Any] | None = None


class InvitationAcceptResponse(BaseSchema):
    project_id: int
    success: SuccessPayload
