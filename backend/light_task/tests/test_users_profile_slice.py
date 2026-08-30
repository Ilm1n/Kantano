from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from tests.registration_helpers import register_and_confirm

PASSWORD = "VeryStrongPass123!"


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(
    client: TestClient,
    *,
    username: str,
    email: str,
    password: str = PASSWORD,
)-> None:
    register_and_confirm(
        client,
        username=username,
        email=email,
        password=password,
    )


def _register_and_login(
    client: TestClient,
    *,
    username: str,
    email: str,
) -> dict:
    suffix = uuid4().hex[:8]
    unique_username = f"{username}_{suffix}"
    local_part, _, domain = email.partition("@")
    unique_email = f"{local_part}+{suffix}@{domain}" if domain else f"{email}_{suffix}"

    _register(
        client,
        username=unique_username,
        email=unique_email,
    )

    login_resp = client.post(
        "/api/auth/login",
        data={"username": unique_username, "password": PASSWORD},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["accessToken"]

    me_resp = client.get(
        "/api/users/me",
        headers=_auth_headers(token),
    )
    assert me_resp.status_code == 200, me_resp.text
    return {"token": token, "user": me_resp.json()}


def _assert_error_code(response, expected_code: str) -> None:
    assert response.json() == {"error": {"code": expected_code}}


def test_confirmed_user_read_response_shape(client: TestClient) -> None:
    payload = _register_and_login(
        client,
        username="profile_user",
        email="profile_user@example.com",
    )["user"]
    assert payload["username"].startswith("profile_user_")
    assert payload["email"].startswith("profile_user+")
    assert payload["isActive"] is True
    assert payload["hasPassword"] is True
    assert payload["fullName"] is None
    assert payload["avatarUrl"] is None


def test_duplicate_registration_returns_conflict(
    client: TestClient,
) -> None:
    suffix = uuid4().hex[:8]
    username = f"duplicate_user_{suffix}"
    email = f"duplicate_user+{suffix}@example.com"
    _register(client, username=username, email=email)
    duplicate_response = client.post(
        "/api/registration",
        json={"username": username, "email": email},
    )

    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["error"]["code"] == "USERNAME_OR_EMAIL_EXISTS"


def test_update_me_and_public_read_response_shape(client: TestClient) -> None:
    user = _register_and_login(
        client,
        username="profile_update_user",
        email="profile_update_user@example.com",
    )

    update_response = client.patch(
        "/api/users/me",
        json={"username": f"renamed_{uuid4().hex[:8]}", "fullName": "Ada Lovelace"},
        headers=_auth_headers(user["token"]),
    )
    assert update_response.status_code == 200, update_response.text
    updated = update_response.json()
    assert updated["fullName"] == "Ada Lovelace"

    public_response = client.get(
        f"/api/users/{updated['id']}",
        headers=_auth_headers(user["token"]),
    )
    assert public_response.status_code == 200, public_response.text
    assert public_response.json() == {
        "id": updated["id"],
        "username": updated["username"],
        "fullName": "Ada Lovelace",
        "avatarUrl": None,
    }


def test_update_username_duplicate_returns_username_taken(client: TestClient) -> None:
    first = _register_and_login(
        client,
        username="profile_first",
        email="profile_first@example.com",
    )
    second = _register_and_login(
        client,
        username="profile_second",
        email="profile_second@example.com",
    )

    response = client.patch(
        "/api/users/me",
        json={"username": first["user"]["username"]},
        headers=_auth_headers(second["token"]),
    )

    assert response.status_code == 409
    _assert_error_code(response, "USERNAME_TAKEN")


def test_password_update_error_codes_are_unchanged(client: TestClient) -> None:
    user = _register_and_login(
        client,
        username="profile_password",
        email="profile_password@example.com",
    )

    missing_current = client.patch(
        "/api/users/me/password",
        json={"newPassword": "NewStrongPass123!"},
        headers=_auth_headers(user["token"]),
    )
    assert missing_current.status_code == 400
    _assert_error_code(missing_current, "CURRENT_PASSWORD_REQUIRED")

    invalid_current = client.patch(
        "/api/users/me/password",
        json={
            "currentPassword": "WrongStrongPass123!",
            "newPassword": "NewStrongPass123!",
        },
        headers=_auth_headers(user["token"]),
    )
    assert invalid_current.status_code == 400
    _assert_error_code(invalid_current, "INVALID_CURRENT_PASSWORD")
