from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from tests.registration_helpers import register_and_confirm

PASSWORD = "VeryStrongPass123!"


def _register(
    client: TestClient,
    *,
    username: str,
    email: str,
) -> None:
    register_and_confirm(
        client,
        username=username,
        email=email,
        password=PASSWORD,
    )


def _assert_error_code(response, expected_code: str) -> None:
    assert response.json() == {"error": {"code": expected_code}}


def test_invalid_password_login_returns_invalid_credentials(
    client: TestClient,
) -> None:
    suffix = uuid4().hex[:8]
    username = f"auth_invalid_{suffix}"
    _register(
        client,
        username=username,
        email=f"auth_invalid+{suffix}@example.com",
    )

    response = client.post(
        "/api/auth/login",
        data={"username": username, "password": "WrongStrongPass123!"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    _assert_error_code(response, "INVALID_CREDENTIALS")


def test_refresh_requires_refresh_cookie(client: TestClient) -> None:
    response = client.post("/api/auth/refresh")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    _assert_error_code(response, "REFRESH_TOKEN_MISSING")


def test_login_refresh_and_logout_cookie_flow(client: TestClient) -> None:
    suffix = uuid4().hex[:8]
    username = f"auth_flow_{suffix}"
    _register(
        client,
        username=username,
        email=f"auth_flow+{suffix}@example.com",
    )

    login_response = client.post(
        "/api/auth/login",
        data={"username": username, "password": PASSWORD},
    )
    assert login_response.status_code == 200, login_response.text
    assert login_response.json()["tokenType"] == "bearer"
    assert "refresh_token" in login_response.cookies

    refresh_response = client.post("/api/auth/refresh")
    assert refresh_response.status_code == 200, refresh_response.text
    assert refresh_response.json()["tokenType"] == "bearer"
    assert "refresh_token" in refresh_response.cookies

    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == 200, logout_response.text
    assert logout_response.json() == {"detail": "Logged out successfully"}
    assert "refresh_token=" in logout_response.headers["set-cookie"]
