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


def _create_column(
    client: TestClient,
    *,
    token: str,
    project_id: int,
    name: str,
) -> dict:
    response = client.post(
        f"/api/projects/{project_id}/columns",
        json={"name": name, "tasksLimit": None},
        headers=_auth_headers(token, str(uuid4())),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_task(
    client: TestClient,
    *,
    token: str,
    project_id: int,
    column_id: int,
    title: str,
) -> dict:
    response = client.post(
        f"/api/projects/{project_id}/columns/{column_id}/tasks",
        json={
            "title": title,
            "description": "read query regression",
            "priority": "MEDIUM",
            "assigneeId": None,
            "tagIds": [],
        },
        headers=_auth_headers(token, str(uuid4())),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _assert_error_code(response, expected_code: str) -> None:
    assert response.json() == {"error": {"code": expected_code}}


def test_project_board_read_response_shape_is_unchanged(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_board_read",
        email="owner_board_read@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Board Read")
    column = _create_column(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Todo",
    )
    task = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=column["id"],
        title="Readable task",
    )

    response = client.get(
        f"/api/projects/{project['id']}/columns",
        headers=_auth_headers(owner["token"]),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == column["id"]
    assert payload[0]["name"] == "Todo"
    assert payload[0]["projectId"] == project["id"]
    assert payload[0]["tasks"][0]["id"] == task["id"]
    assert payload[0]["tasks"][0]["title"] == "Readable task"


def test_project_tasks_read_filters_and_task_details_are_unchanged(
    client: TestClient,
) -> None:
    owner = _register_and_login(
        client,
        username="owner_task_read",
        email="owner_task_read@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Task Read")
    column = _create_column(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Todo",
    )
    task = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=column["id"],
        title="Needle task",
    )
    _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=column["id"],
        title="Other task",
    )

    list_response = client.get(
        f"/api/projects/{project['id']}/tasks",
        params={"search": "Needle"},
        headers=_auth_headers(owner["token"]),
    )
    assert list_response.status_code == 200, list_response.text
    assert [item["id"] for item in list_response.json()] == [task["id"]]

    detail_response = client.get(
        f"/api/tasks/{task['id']}",
        headers=_auth_headers(owner["token"]),
    )
    assert detail_response.status_code == 200, detail_response.text
    payload = detail_response.json()
    assert payload["id"] == task["id"]
    assert payload["description"] == "read query regression"
    assert payload["authorId"] == owner["user"]["id"]


def test_non_member_project_board_read_returns_project_not_found(
    client: TestClient,
) -> None:
    owner = _register_and_login(
        client,
        username="owner_board_denied",
        email="owner_board_denied@example.com",
    )
    outsider = _register_and_login(
        client,
        username="outsider_board_denied",
        email="outsider_board_denied@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Denied Board")

    response = client.get(
        f"/api/projects/{project['id']}/columns",
        headers=_auth_headers(outsider["token"]),
    )

    assert response.status_code == 404
    _assert_error_code(response, "PROJECT_NOT_FOUND")


def test_non_member_task_details_read_returns_insufficient_permissions(
    client: TestClient,
) -> None:
    owner = _register_and_login(
        client,
        username="owner_task_denied",
        email="owner_task_denied@example.com",
    )
    outsider = _register_and_login(
        client,
        username="outsider_task_denied",
        email="outsider_task_denied@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Denied Task")
    column = _create_column(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Todo",
    )
    task = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=column["id"],
        title="Private task",
    )

    response = client.get(
        f"/api/tasks/{task['id']}",
        headers=_auth_headers(outsider["token"]),
    )

    assert response.status_code == 403
    _assert_error_code(response, "INSUFFICIENT_PERMISSIONS")
