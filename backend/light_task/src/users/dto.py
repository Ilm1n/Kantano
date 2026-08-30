from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.users.models import User


@dataclass(frozen=True, kw_only=True)
class GetUserQuery:
    user_id: int


@dataclass(frozen=True, kw_only=True)
class UpdateUserCommand:
    user_id: int
    changes: dict[str, Any]


@dataclass(frozen=True, kw_only=True)
class UpdateUserPasswordCommand:
    user_id: int
    current_password: str | None
    new_password: str


@dataclass(frozen=True, kw_only=True)
class UploadAvatarCommand:
    user_id: int
    file_data: bytes
    extension: str
    mime_type: str


@dataclass(frozen=True, kw_only=True)
class DeleteAvatarCommand:
    user_id: int


@dataclass(frozen=True, kw_only=True)
class AvatarMutationResult:
    user: User
    old_avatar_object_key: str | None = None
