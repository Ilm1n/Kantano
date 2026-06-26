from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import src.security as security
from src.projects.constants import ProjectRole
from src.projects.models import ProjectMember
from src.users.models import User


@dataclass
class WsAuthContext:
    user_id: int
    username: str | None
    email: str | None
    expires_at: datetime | None


class WsAuthError(Exception):
    pass


def validate_access_token(token: str) -> WsAuthContext:
    try:
        payload = security.decode_jwt(token)
    except security.TokenDecodeError as exc:
        raise WsAuthError(str(exc.code)) from exc

    if payload.get("type") != security.ACCESS_TOKEN_TYPE:
        raise WsAuthError("INVALID_TOKEN_TYPE")

    user_id = payload.get("sub")
    if not user_id:
        raise WsAuthError("INVALID_TOKEN_PAYLOAD")

    exp = payload.get("exp")
    expires_at: datetime | None = None
    if isinstance(exp, (int, float)):
        expires_at = datetime.fromtimestamp(exp, tz=UTC)

    return WsAuthContext(
        user_id=int(user_id),
        username=payload.get("username"),
        email=payload.get("email"),
        expires_at=expires_at,
    )


async def ensure_user_is_active(session: AsyncSession, *, user_id: int) -> bool:
    user = await session.get(User, user_id)
    return bool(user and user.is_active)


async def get_project_role(
    session: AsyncSession,
    *,
    project_id: int,
    user_id: int,
) -> ProjectRole | None:
    stmt = select(ProjectMember.role).where(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
    )
    return await session.scalar(stmt)


def parse_auth_message(raw: Any) -> str:
    if not isinstance(raw, dict):
        raise WsAuthError("INVALID_AUTH_MESSAGE")

    if raw.get("type") != "auth":
        raise WsAuthError("AUTH_REQUIRED")

    token = raw.get("accessToken")
    if not isinstance(token, str) or not token:
        raise WsAuthError("TOKEN_REQUIRED")

    return token
