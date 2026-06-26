from __future__ import annotations

from fastapi import Response

import src.security as security
from src.auth.dto import TokenResult
from src.auth.schemas import Token
from src.config import settings
from src.users.models import User


def create_token_result(user: User) -> TokenResult:
    token_payload = {
        "sub": str(user.id),
        "username": user.username,
        "email": user.email,
        "is_active": user.is_active,
    }
    return TokenResult(
        access_token=security.create_access_token(user_data=token_payload),
        refresh_token=security.create_refresh_token(user_id=user.id),
        token_type="bearer",  # noqa: S106
    )


def apply_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.auth_jwt.secure,
        samesite="lax",
        path="/",
        max_age=settings.auth_jwt.refresh_token_expire_days * 24 * 60 * 60,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key="refresh_token",
        path="/",
        httponly=True,
        samesite="lax",
    )


def token_response(result: TokenResult) -> Token:
    return Token(
        access_token=result.access_token,
        token_type=result.token_type,
    )
