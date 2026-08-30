from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from src.auth.repository import AuthRepository
from src.auth.yandex import (
    YandexCallbackResult,
    YandexOAuthClient,
    YandexOAuthError,
    build_yandex_start_result,
    validate_yandex_state,
)
from src.db.unit_of_work import UnitOfWork
from src.logger import auth_logger


class StartYandexAuthUseCase:
    def execute(self, next_path: str | None):
        return build_yandex_start_result(next_path)


class YandexCallbackUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        oauth_client: YandexOAuthClient,
    ) -> None:
        self._uow_factory = uow_factory
        self._oauth_client = oauth_client

    async def execute(
        self,
        *,
        code: str | None,
        state: str | None,
        state_cookie: str | None,
    ) -> YandexCallbackResult:
        next_path = validate_yandex_state(state=state, state_cookie=state_cookie)
        if not code:
            raise YandexOAuthError("missing_code")

        access_token = await self._oauth_client._exchange_code_for_token(code)
        profile = await self._oauth_client._fetch_profile(access_token)

        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = AuthRepository(uow.session)
                user = await repository.get_user_by_yandex_id(profile.yandex_id)
                if user is not None:
                    return YandexCallbackResult(user=user, next_path=next_path)

                user = await repository.get_user_by_email(profile.email)
                if user is not None:
                    if user.yandex_id and user.yandex_id != profile.yandex_id:
                        raise YandexOAuthError("email_already_linked")
                    if user.email_verified_at is None:
                        raise YandexOAuthError("email_not_verified")
                    user.yandex_id = profile.yandex_id
                    if not user.full_name and profile.full_name:
                        user.full_name = profile.full_name
                    repository.save_user(user)
                    await repository.flush()
                    await repository.refresh_user(user)
                    return YandexCallbackResult(user=user, next_path=next_path)

                username = await self._build_unique_username(
                    repository,
                    profile.username,
                )
                user = repository.add_yandex_user(
                    email=profile.email,
                    username=username,
                    full_name=profile.full_name,
                    yandex_id=profile.yandex_id,
                    email_verified_at=datetime.now(UTC),
                )
                await repository.flush()
                await repository.refresh_user(user)
                await repository.delete_pending_by_email(profile.email)
                return YandexCallbackResult(user=user, next_path=next_path)
        except YandexOAuthError:
            raise
        except IntegrityError as exc:
            auth_logger.exception("Failed to save Yandex user")
            raise YandexOAuthError("account_save_failed") from exc

    async def _build_unique_username(
        self,
        repository: AuthRepository,
        base_username: str,
    ) -> str:
        base = base_username[:50]
        username = base
        suffix = 1

        while await repository.username_exists(username):
            suffix_text = f"_{suffix}"
            username = f"{base[: 50 - len(suffix_text)]}{suffix_text}"
            suffix += 1

        return username
