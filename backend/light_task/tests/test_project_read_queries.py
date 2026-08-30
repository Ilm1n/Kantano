from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from tests.registration_helpers import register_and_confirm

PASSWORD = "VeryStrongPass123!"


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

    register_and_confirm(
        client,
        username=unique_username,
        email=unique_email,
        password=PASSWORD,
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


def _auth_headers(token: str, client_mutation_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if client_mutation_id:
        headers["X-Client-Mutation-Id"] = client_mutation_id
    return headers


def _create_project(client: TestClient, *, token: str, name: str) -> dict:
    response = client.post(
        "/api/projects/",
        json={"name": name, "description": None, "color": "#3B82F6"},
        headers=_auth_headers(token, str(uuid4())),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _add_member_via_invite(
    client: TestClient,
    *,
    owner_token: str,
    member_token: str,
    project_id: int,
) -> None:
    invite_resp = client.post(
        f"/api/projects/{project_id}/invite",
        json={"role": "MEMBER", "email": None, "maxUses": 1, "expiresInDays": 7},
        headers=_auth_headers(owner_token, str(uuid4())),
    )
    assert invite_resp.status_code == 201, invite_resp.text

    accept_resp = client.post(
        f"/api/invitations/{invite_resp.json()['token']}/accept",
        headers=_auth_headers(member_token, str(uuid4())),
    )
    assert accept_resp.status_code == 200, accept_resp.text


def _assert_error_code(response, expected_code: str) -> None:
    assert response.json() == {"error": {"code": expected_code}}


def test_project_list_details_and_members_response_shape(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_project_read",
        email="owner_project_read@example.com",
    )
    member = _register_and_login(
        client,
        username="member_project_read",
        email="member_project_read@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Project Read")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )

    list_response = client.get(
        "/api/projects/",
        headers=_auth_headers(owner["token"]),
    )
    assert list_response.status_code == 200, list_response.text
    assert list_response.json()[0]["id"] == project["id"]
    assert list_response.json()[0]["currentUserRole"] == "OWNER"

    details_response = client.get(
        f"/api/projects/{project['id']}",
        headers=_auth_headers(member["token"]),
    )
    assert details_response.status_code == 200, details_response.text
    assert details_response.json()["id"] == project["id"]
    assert details_response.json()["currentUserRole"] == "MEMBER"

    members_response = client.get(
        f"/api/projects/{project['id']}/members",
        headers=_auth_headers(owner["token"]),
    )
    assert members_response.status_code == 200, members_response.text
    members = members_response.json()
    assert [item["user"]["id"] for item in members] == [
        owner["user"]["id"],
        member["user"]["id"],
    ]
    assert members[0]["role"] == "OWNER"
    assert members[1]["role"] == "MEMBER"


def test_non_member_project_details_and_members_return_project_not_found(
    client: TestClient,
) -> None:
    owner = _register_and_login(
        client,
        username="owner_project_read_denied",
        email="owner_project_read_denied@example.com",
    )
    outsider = _register_and_login(
        client,
        username="outsider_project_read_denied",
        email="outsider_project_read_denied@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Project Denied")

    details_response = client.get(
        f"/api/projects/{project['id']}",
        headers=_auth_headers(outsider["token"]),
    )
    assert details_response.status_code == 404
    _assert_error_code(details_response, "PROJECT_NOT_FOUND")

    members_response = client.get(
        f"/api/projects/{project['id']}/members",
        headers=_auth_headers(outsider["token"]),
    )
    assert members_response.status_code == 404
    _assert_error_code(members_response, "PROJECT_NOT_FOUND")
