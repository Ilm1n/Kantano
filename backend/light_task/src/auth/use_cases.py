from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

import src.security as security
from src.auth.dto import LoginCommand, RefreshTokenCommand, TokenResult
from src.auth.repository import AuthRepository
from src.auth.tokens import create_token_result
from src.errors import ErrorCode
from src.logger import auth_logger
from src.shared.errors import AppError, DatabaseError, ForbiddenError, UnauthorizedError
from src.users.passwords import validate_password


class LoginUseCase:
    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def execute(self, command: LoginCommand) -> TokenResult:
        try:
            async with self._session_factory() as session:
                repository = AuthRepository(session)
                user = await repository.get_user_by_username_or_email(command.username_or_email)
                if user is None:
                    auth_logger.warning(
                        "Failed login attempt for %s",
                        command.username_or_email,
                    )
                    raise UnauthorizedError(ErrorCode.INVALID_CREDENTIALS)

                if user.email_verified_at is None:
                    raise ForbiddenError(ErrorCode.EMAIL_NOT_VERIFIED)

                if not user.hashed_password:
                    raise UnauthorizedError(ErrorCode.PASSWORD_LOGIN_UNAVAILABLE)

                if not validate_password(command.password, user.hashed_password):
                    auth_logger.warning(
                        "Failed login attempt for %s",
                        command.username_or_email,
                    )
                    raise UnauthorizedError(ErrorCode.INVALID_CREDENTIALS)

                auth_logger.info("Token issued for user %s", user.id)
                return create_token_result(user)
        except AppError:
            raise
        except Exception as exc:
            auth_logger.exception(
                "Failed to authenticate user %s",
                command.username_or_email,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class RefreshTokenUseCase:
    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def execute(self, command: RefreshTokenCommand) -> TokenResult:
        try:
            if not command.refresh_token:
                auth_logger.warning("Refresh token missing in request")
                raise UnauthorizedError(ErrorCode.REFRESH_TOKEN_MISSING)

            try:
                payload = security.decode_jwt(command.refresh_token)
            except security.TokenDecodeError as exc:
                raise UnauthorizedError(exc.code) from exc

            if payload.get("type") != security.REFRESH_TOKEN_TYPE:
                auth_logger.warning("Invalid refresh token type")
                raise UnauthorizedError(ErrorCode.INVALID_TOKEN_TYPE)

            user_id = payload.get("sub")
            if not user_id:
                auth_logger.warning("Invalid refresh token payload - missing user_id")
                raise UnauthorizedError(ErrorCode.INVALID_TOKEN_PAYLOAD)

            async with self._session_factory() as session:
                repository = AuthRepository(session)
                user = await repository.get_user(int(user_id))
                if user is None:
                    raise UnauthorizedError(ErrorCode.USER_NOT_FOUND)
                if not user.is_active:
                    raise ForbiddenError(ErrorCode.INACTIVE_USER)
                if user.email_verified_at is None:
                    raise ForbiddenError(ErrorCode.EMAIL_NOT_VERIFIED)

                auth_logger.info("Token issued for user %s", user.id)
                return create_token_result(user)
        except AppError:
            raise
        except Exception as exc:
            auth_logger.exception("Failed to refresh token", exc_info=exc)
            raise DatabaseError() from exc
