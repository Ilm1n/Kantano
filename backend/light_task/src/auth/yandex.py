from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from src.config import settings
from src.errors import ErrorCode
from src.logger import auth_logger
from src.shared.errors import ServiceUnavailableError
from src.users.models import User

DEFAULT_NEXT_PATH = "/projects"
FRONTEND_CALLBACK_PATH = "/auth/yandex/callback"


@dataclass(frozen=True)
class YandexProfile:
    yandex_id: str
    email: str
    username: str
    full_name: str | None


@dataclass(frozen=True)
class YandexStartResult:
    authorize_url: str
    state_cookie_value: str
    state_cookie_max_age_seconds: int


@dataclass(frozen=True)
class YandexCallbackResult:
    user: User
    next_path: str


class YandexOAuthError(Exception):
    def __init__(self, code: str):
        self.code = code


class YandexOAuthClient:
    async def _exchange_code_for_token(self, code: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    settings.yandex.token_url,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "client_id": settings.yandex.client_id,
                        "client_secret": settings.yandex.client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.HTTPError as err:
            auth_logger.exception("Yandex token request failed")
            raise YandexOAuthError("token_request_failed") from err

        if response.status_code != 200:
            auth_logger.warning("Yandex token exchange failed: %s", response.text)
            raise YandexOAuthError("invalid_code")

        token_data = response.json()
        access_token = token_data.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise YandexOAuthError("missing_yandex_token")
        return access_token

    async def _fetch_profile(self, access_token: str) -> YandexProfile:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    settings.yandex.userinfo_url,
                    params={"format": "json"},
                    headers={"Authorization": f"OAuth {access_token}"},
                )
        except httpx.HTTPError as err:
            auth_logger.exception("Yandex profile request failed")
            raise YandexOAuthError("profile_request_failed") from err

        if response.status_code != 200:
            auth_logger.warning("Yandex profile request failed: %s", response.text)
            raise YandexOAuthError("profile_request_failed")

        return parse_yandex_profile(response.json())


def get_yandex_oauth_client() -> YandexOAuthClient:
    return YandexOAuthClient()


def ensure_yandex_configured() -> None:
    if settings.yandex.client_id and settings.yandex.client_secret:
        return
    raise ServiceUnavailableError(ErrorCode.UNKNOWN_ERROR)


def build_yandex_start_result(next_path: str | None) -> YandexStartResult:
    ensure_yandex_configured()
    safe_next = safe_next_path(next_path)
    state = secrets.token_urlsafe(32)
    cookie_value = f"{state}|{safe_next}"
    query = urlencode({"response_type": "code", "client_id": settings.yandex.client_id, "redirect_uri": settings.yandex.redirect_uri, "state": state})
    url = f"{settings.yandex.authorize_url}?{query}"
    return YandexStartResult(
        authorize_url=url,
        state_cookie_value=cookie_value,
        state_cookie_max_age_seconds=settings.yandex.state_cookie_max_age_seconds,
    )


def validate_yandex_state(state: str | None, state_cookie: str | None) -> str:
    if not state or not state_cookie:
        raise YandexOAuthError("invalid_state")

    cookie_state, separator, next_path = state_cookie.partition("|")
    if not separator or not secrets.compare_digest(cookie_state, state):
        raise YandexOAuthError("invalid_state")

    return safe_next_path(next_path)


def build_frontend_success_url(next_path: str) -> str:
    return frontend_url(FRONTEND_CALLBACK_PATH, {"next": safe_next_path(next_path)})


def build_frontend_error_url(error_code: str) -> str:
    return frontend_url("/login", {"oauth_error": error_code})


def safe_next_path(next_path: str | None) -> str:
    if not next_path:
        return DEFAULT_NEXT_PATH
    if not next_path.startswith("/") or next_path.startswith("//"):
        return DEFAULT_NEXT_PATH
    return next_path


def frontend_url(path: str, query: dict[str, str]) -> str:
    base_url = settings.frontend.base_url.rstrip("/")
    return f"{base_url}{path}?{urlencode(query)}"


def parse_yandex_profile(data: dict[str, Any]) -> YandexProfile:
    yandex_id = str(data.get("id") or "").strip()
    email = str(data.get("default_email") or "").strip().lower()

    if not yandex_id:
        raise YandexOAuthError("missing_yandex_id")
    if not email:
        raise YandexOAuthError("missing_email")

    username = normalize_username(
        data.get("login") or data.get("display_name") or email.split("@", 1)[0]
    )
    full_name = data.get("real_name") or data.get("display_name")
    if isinstance(full_name, str):
        full_name = full_name.strip() or None
    else:
        full_name = None

    return YandexProfile(
        yandex_id=yandex_id,
        email=email,
        username=username,
        full_name=full_name,
    )


def normalize_username(value: Any) -> str:
    username = str(value or "").strip().lower()
    username = re.sub(r"[^a-z0-9_]+", "_", username)
    username = re.sub(r"_+", "_", username).strip("_")
    return username[:50] or "yandex_user"
