from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import select

from src.auth.yandex import YandexOAuthClient, YandexOAuthError, YandexProfile
from src.db.database import db_helper
from src.security import hash_password
from src.users.models import User
from tests.registration_helpers import register_and_confirm

PASSWORD = "VeryStrongPass123!"


def _state_from_start_response(client: TestClient, next_path: str = "/projects") -> str:
    response = client.get(
        "/api/auth/yandex/start",
        params={"next": next_path},
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text

    location = response.headers["location"]
    query = parse_qs(urlparse(location).query)
    return query["state"][0]


async def _fake_exchange_code_for_token(self: YandexOAuthClient, code: str) -> str:
    if code == "bad-code":
        raise YandexOAuthError("invalid_code")
    return "yandex-access-token"


async def _fake_fetch_profile(
    self: YandexOAuthClient,
    access_token: str,
) -> YandexProfile:
    return YandexProfile(
        yandex_id="yandex-123",
        email="yandex-user@example.com",
        username="ivan",
        full_name="Ivan Ivanov",
    )


async def _fake_fetch_profile_without_email(
    self: YandexOAuthClient,
    access_token: str,
) -> YandexProfile:
    raise YandexOAuthError("missing_email")


def _patch_yandex_success(monkeypatch) -> None:
    monkeypatch.setattr(
        YandexOAuthClient,
        "_exchange_code_for_token",
        _fake_exchange_code_for_token,
    )
    monkeypatch.setattr(
        YandexOAuthClient,
        "_fetch_profile",
        _fake_fetch_profile,
    )


async def _get_user_by_email(email: str) -> User | None:
    async with db_helper.async_session_maker() as session:
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()


async def _create_local_user(
    *,
    username: str,
    email: str,
    yandex_id: str | None = None,
    email_verified: bool = True,
) -> User:
    async with db_helper.async_session_maker() as session:
        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(PASSWORD),
            yandex_id=yandex_id,
            email_verified_at=datetime.now(UTC) if email_verified else None,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


def test_yandex_callback_creates_new_user(client: TestClient, monkeypatch) -> None:
    _patch_yandex_success(monkeypatch)
    state = _state_from_start_response(client)

    response = client.get(
        "/api/auth/yandex/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302, response.text
    assert response.headers["location"] == (
        "http://localhost:5173/auth/yandex/callback?next=%2Fprojects"
    )

    cookies = SimpleCookie(response.headers["set-cookie"])
    assert "refresh_token" in cookies

    user = asyncio.run(_get_user_by_email("yandex-user@example.com"))
    assert user is not None
    assert user.yandex_id == "yandex-123"
    assert user.username == "ivan"
    assert user.hashed_password is None
    assert user.email_verified_at is not None


def test_yandex_callback_auto_links_existing_user_by_email(
    client: TestClient,
    monkeypatch,
) -> None:
    _patch_yandex_success(monkeypatch)
    local_user = asyncio.run(
        _create_local_user(
            username="existing",
            email="yandex-user@example.com",
        )
    )
    state = _state_from_start_response(client)

    response = client.get(
        "/api/auth/yandex/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302, response.text
    user = asyncio.run(_get_user_by_email("yandex-user@example.com"))
    assert user is not None
    assert user.id == local_user.id
    assert user.yandex_id == "yandex-123"
    assert user.hashed_password is not None


def test_yandex_callback_rejects_unverified_local_email(
    client: TestClient,
    monkeypatch,
) -> None:
    _patch_yandex_success(monkeypatch)
    asyncio.run(
        _create_local_user(
            username="unverified",
            email="yandex-user@example.com",
            email_verified=False,
        )
    )
    state = _state_from_start_response(client)

    response = client.get(
        "/api/auth/yandex/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert (
        response.headers["location"] == "http://localhost:5173/login?oauth_error=email_not_verified"
    )


def test_yandex_callback_uses_linked_user_by_yandex_id(
    client: TestClient,
    monkeypatch,
) -> None:
    _patch_yandex_success(monkeypatch)
    linked_user = asyncio.run(
        _create_local_user(
            username="linked",
            email="different@example.com",
            yandex_id="yandex-123",
        )
    )
    state = _state_from_start_response(client)

    response = client.get(
        "/api/auth/yandex/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302, response.text
    user = asyncio.run(_get_user_by_email("different@example.com"))
    assert user is not None
    assert user.id == linked_user.id


def test_yandex_callback_adds_suffix_when_username_is_taken(
    client: TestClient,
    monkeypatch,
) -> None:
    _patch_yandex_success(monkeypatch)
    asyncio.run(
        _create_local_user(
            username="ivan",
            email="ivan-local@example.com",
        )
    )
    state = _state_from_start_response(client)

    response = client.get(
        "/api/auth/yandex/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302, response.text
    user = asyncio.run(_get_user_by_email("yandex-user@example.com"))
    assert user is not None
    assert user.username == "ivan_1"


def test_yandex_callback_rejects_invalid_state(
    client: TestClient,
    monkeypatch,
) -> None:
    _patch_yandex_success(monkeypatch)
    _state_from_start_response(client)

    response = client.get(
        "/api/auth/yandex/callback",
        params={"code": "valid-code", "state": "wrong-state"},
        follow_redirects=False,
    )

    assert response.status_code == 302, response.text
    assert response.headers["location"] == ("http://localhost:5173/login?oauth_error=invalid_state")


def test_yandex_callback_handles_invalid_code(
    client: TestClient,
    monkeypatch,
) -> None:
    _patch_yandex_success(monkeypatch)
    state = _state_from_start_response(client)

    response = client.get(
        "/api/auth/yandex/callback",
        params={"code": "bad-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302, response.text
    assert response.headers["location"] == ("http://localhost:5173/login?oauth_error=invalid_code")


def test_yandex_callback_requires_email(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        YandexOAuthClient,
        "_exchange_code_for_token",
        _fake_exchange_code_for_token,
    )
    monkeypatch.setattr(
        YandexOAuthClient,
        "_fetch_profile",
        _fake_fetch_profile_without_email,
    )
    state = _state_from_start_response(client)

    response = client.get(
        "/api/auth/yandex/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302, response.text
    assert response.headers["location"] == ("http://localhost:5173/login?oauth_error=missing_email")


def test_password_login_still_works(client: TestClient) -> None:
    register_and_confirm(
        client,
        username="password_user",
        email="password-user@example.com",
        password=PASSWORD,
    )

    response = client.post(
        "/api/auth/login",
        data={
            "username": "password_user",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["accessToken"]


def test_yandex_user_can_set_password_and_use_password_login(
    client: TestClient,
    monkeypatch,
) -> None:
    _patch_yandex_success(monkeypatch)
    state = _state_from_start_response(client)

    callback_response = client.get(
        "/api/auth/yandex/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )
    assert callback_response.status_code == 302, callback_response.text

    login_response = client.post(
        "/api/auth/login",
        data={
            "username": "ivan",
            "password": PASSWORD,
        },
    )
    assert login_response.status_code == 401, login_response.text
    assert login_response.json()["error"]["code"] == "PASSWORD_LOGIN_UNAVAILABLE"

    refresh_response = client.post("/api/auth/refresh")
    assert refresh_response.status_code == 200, refresh_response.text
    access_token = refresh_response.json()["accessToken"]

    password_response = client.patch(
        "/api/users/me/password",
        json={"newPassword": PASSWORD},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert password_response.status_code == 200, password_response.text
    assert password_response.json()["hasPassword"] is True

    login_response = client.post(
        "/api/auth/login",
        data={
            "username": "ivan",
            "password": PASSWORD,
        },
    )
    assert login_response.status_code == 200, login_response.text
    assert login_response.json()["accessToken"]


def test_password_update_requires_current_password_for_password_user(
    client: TestClient,
) -> None:
    register_and_confirm(
        client,
        username="password_update_user",
        email="password-update-user@example.com",
        password=PASSWORD,
    )

    login_response = client.post(
        "/api/auth/login",
        data={
            "username": "password_update_user",
            "password": PASSWORD,
        },
    )
    assert login_response.status_code == 200, login_response.text
    access_token = login_response.json()["accessToken"]

    password_response = client.patch(
        "/api/users/me/password",
        json={"newPassword": "NewVeryStrongPass123!"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert password_response.status_code == 400, password_response.text
    assert password_response.json()["error"]["code"] == "CURRENT_PASSWORD_REQUIRED"

    password_response = client.patch(
        "/api/users/me/password",
        json={
            "currentPassword": "wrong-password",
            "newPassword": "NewVeryStrongPass123!",
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert password_response.status_code == 400, password_response.text
    assert password_response.json()["error"]["code"] == "INVALID_CURRENT_PASSWORD"

    password_response = client.patch(
        "/api/users/me/password",
        json={
            "currentPassword": PASSWORD,
            "newPassword": "NewVeryStrongPass123!",
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert password_response.status_code == 200, password_response.text
