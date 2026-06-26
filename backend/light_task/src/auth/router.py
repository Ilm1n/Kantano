from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Query, Response
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm

from src.auth import schemas
from src.auth.dto import LoginCommand, RefreshTokenCommand
from src.auth.tokens import (
    apply_refresh_cookie,
    clear_refresh_cookie,
    create_token_result,
    token_response,
)
from src.auth.use_cases import LoginUseCase, RefreshTokenUseCase
from src.auth.yandex import (
    YandexOAuthClient,
    YandexOAuthError,
    build_frontend_error_url,
    build_frontend_success_url,
    get_yandex_oauth_client,
)
from src.auth.yandex_use_cases import StartYandexAuthUseCase, YandexCallbackUseCase
from src.config import settings
from src.db.database import db_helper
from src.db.unit_of_work import UnitOfWork

router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
)


def get_login_use_case() -> LoginUseCase:
    return LoginUseCase(db_helper.async_session_maker)


def get_refresh_token_use_case() -> RefreshTokenUseCase:
    return RefreshTokenUseCase(db_helper.async_session_maker)


def get_start_yandex_auth_use_case() -> StartYandexAuthUseCase:
    return StartYandexAuthUseCase()


def get_yandex_callback_use_case(
    oauth_client: Annotated[YandexOAuthClient, Depends(get_yandex_oauth_client)],
) -> YandexCallbackUseCase:
    return YandexCallbackUseCase(
        lambda: UnitOfWork(),
        oauth_client,
    )


def clear_yandex_state_cookie(response: RedirectResponse) -> None:
    response.delete_cookie(
        key=settings.yandex.state_cookie_name,
        path="/api/auth/yandex",
        httponly=True,
        samesite="lax",
    )


@router.post(
    "/login",
    response_model=schemas.Token,
)
async def login_for_access_token(
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    use_case: Annotated[LoginUseCase, Depends(get_login_use_case)],
):
    command = LoginCommand(
        username_or_email=form_data.username,
        password=form_data.password,
    )
    result = await use_case.execute(command)
    apply_refresh_cookie(response, result.refresh_token)
    return token_response(result)


@router.get("/yandex/start", include_in_schema=False)
async def start_yandex_auth(
    use_case: Annotated[StartYandexAuthUseCase, Depends(get_start_yandex_auth_use_case)],
    next_path: Annotated[str | None, Query(alias="next")] = None,
) -> RedirectResponse:
    result = use_case.execute(next_path)
    response = RedirectResponse(url=result.authorize_url, status_code=302)
    response.set_cookie(
        key=settings.yandex.state_cookie_name,
        value=result.state_cookie_value,
        httponly=True,
        secure=settings.auth_jwt.secure,
        samesite="lax",
        path="/api/auth/yandex",
        max_age=result.state_cookie_max_age_seconds,
    )
    return response


@router.get("/yandex/callback", include_in_schema=False)
async def yandex_auth_callback(
    use_case: Annotated[YandexCallbackUseCase, Depends(get_yandex_callback_use_case)],
    code: str | None = None,
    state: str | None = None,
    state_cookie: Annotated[
        str | None,
        Cookie(alias=settings.yandex.state_cookie_name),
    ] = None,
) -> RedirectResponse:
    try:
        result = await use_case.execute(
            code=code,
            state=state,
            state_cookie=state_cookie,
        )
    except YandexOAuthError as exc:
        response = RedirectResponse(
            url=build_frontend_error_url(exc.code),
            status_code=302,
        )
        clear_yandex_state_cookie(response)
        return response

    response = RedirectResponse(
        url=build_frontend_success_url(result.next_path),
        status_code=302,
    )
    clear_yandex_state_cookie(response)
    token_result = create_token_result(result.user)
    apply_refresh_cookie(response, token_result.refresh_token)
    return response


@router.post(
    "/refresh",
    response_model=schemas.Token,
)
async def refresh_jwt(
    response: Response,
    use_case: Annotated[RefreshTokenUseCase, Depends(get_refresh_token_use_case)],
    refresh_token: Annotated[str | None, Cookie()] = None,
):
    command = RefreshTokenCommand(refresh_token=refresh_token)
    result = await use_case.execute(command)
    apply_refresh_cookie(response, result.refresh_token)
    return token_response(result)


@router.post("/logout")
async def logout(
    response: Response,
):
    clear_refresh_cookie(response)
    return {"detail": "Logged out successfully"}
