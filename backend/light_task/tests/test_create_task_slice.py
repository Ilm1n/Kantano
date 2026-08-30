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
    name: str = "Todo",
    tasks_limit: int | None = None,
) -> dict:
    response = client.post(
        f"/api/projects/{project_id}/columns",
        json={"name": name, "tasksLimit": tasks_limit},
        headers=_auth_headers(token, str(uuid4())),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_tag(
    client: TestClient,
    *,
    token: str,
    project_id: int,
    name: str,
) -> dict:
    response = client.post(
        f"/api/projects/{project_id}/tags",
        json={"name": name, "color": "#9CA3AF"},
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


def _promote_member_to_manager(
    client: TestClient,
    *,
    owner_token: str,
    project_id: int,
    user_id: int,
) -> None:
    response = client.patch(
        f"/api/projects/{project_id}/members/{user_id}",
        json={"role": "MANAGER"},
        headers=_auth_headers(owner_token, str(uuid4())),
    )
    assert response.status_code == 200, response.text


def _create_task(
    client: TestClient,
    *,
    token: str,
    project_id: int,
    column_id: int,
    title: str = "Task",
    assignee_id: int | None = None,
    tag_ids: list[int] | None = None,
) -> object:
    return client.post(
        f"/api/projects/{project_id}/columns/{column_id}/tasks",
        json={
            "title": title,
            "description": "created via api",
            "priority": "MEDIUM",
            "assigneeId": assignee_id,
            "tagIds": tag_ids or [],
        },
        headers=_auth_headers(token, str(uuid4())),
    )


def _assert_error_code(response, expected_code: str) -> None:
    assert response.json() == {"error": {"code": expected_code}}


def test_owner_can_create_task_with_unchanged_response_shape(
    client: TestClient,
) -> None:
    owner = _register_and_login(
        client,
        username="owner_create_task",
        email="owner_create_task@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Create Task")
    column = _create_column(client, token=owner["token"], project_id=project["id"])
    tag = _create_tag(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Backend",
    )

    response = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=column["id"],
        title="Owner task",
        tag_ids=[tag["id"]],
    )

    assert response.status_code == 201, response.text
    task = response.json()
    assert task["title"] == "Owner task"
    assert task["description"] == "created via api"
    assert task["priority"] == "MEDIUM"
    assert task["projectId"] == project["id"]
    assert task["columnId"] == column["id"]
    assert task["authorId"] == owner["user"]["id"]
    assert task["assigneeId"] is None
    assert task["tags"] == [tag]
    assert isinstance(task["position"], float)
    assert isinstance(task["createdAt"], str)
    assert isinstance(task["updatedAt"], str)


def test_manager_can_create_task(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_manager_create",
        email="owner_manager_create@example.com",
    )
    manager = _register_and_login(
        client,
        username="manager_create",
        email="manager_create@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Manager Create")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=manager["token"],
        project_id=project["id"],
    )
    _promote_member_to_manager(
        client,
        owner_token=owner["token"],
        project_id=project["id"],
        user_id=manager["user"]["id"],
    )
    column = _create_column(client, token=owner["token"], project_id=project["id"])

    response = _create_task(
        client,
        token=manager["token"],
        project_id=project["id"],
        column_id=column["id"],
    )

    assert response.status_code == 201, response.text


def test_member_can_create_task_assigned_to_self(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_member_self",
        email="owner_member_self@example.com",
    )
    member = _register_and_login(
        client,
        username="member_self",
        email="member_self@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Member Self")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )
    column = _create_column(client, token=owner["token"], project_id=project["id"])

    response = _create_task(
        client,
        token=member["token"],
        project_id=project["id"],
        column_id=column["id"],
        assignee_id=member["user"]["id"],
    )

    assert response.status_code == 201, response.text
    assert response.json()["assigneeId"] == member["user"]["id"]


def test_member_cannot_create_task_assigned_to_another_user(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_member_other",
        email="owner_member_other@example.com",
    )
    member = _register_and_login(
        client,
        username="member_other",
        email="member_other@example.com",
    )
    other_member = _register_and_login(
        client,
        username="other_member",
        email="other_member@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Member Other")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=other_member["token"],
        project_id=project["id"],
    )
    column = _create_column(client, token=owner["token"], project_id=project["id"])

    response = _create_task(
        client,
        token=member["token"],
        project_id=project["id"],
        column_id=column["id"],
        assignee_id=other_member["user"]["id"],
    )

    assert response.status_code == 403, response.text
    _assert_error_code(response, "MEMBERS_ONLY_OWN_TASKS")


def test_create_task_rejects_assignee_outside_project(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_assignee_outside",
        email="owner_assignee_outside@example.com",
    )
    outsider = _register_and_login(
        client,
        username="outsider_assignee",
        email="outsider_assignee@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Outside Assignee")
    column = _create_column(client, token=owner["token"], project_id=project["id"])

    response = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=column["id"],
        assignee_id=outsider["user"]["id"],
    )

    assert response.status_code == 400, response.text
    _assert_error_code(response, "ASSIGNEE_NOT_PROJECT_MEMBER")


def test_create_task_rejects_invalid_tag_ids(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_invalid_tags",
        email="owner_invalid_tags@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Invalid Tags")
    column = _create_column(client, token=owner["token"], project_id=project["id"])

    response = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=column["id"],
        tag_ids=[999999],
    )

    assert response.status_code == 400, response.text
    _assert_error_code(response, "INVALID_TAG_IDS")


def test_create_task_respects_column_task_limit(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_task_limit",
        email="owner_task_limit@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Task Limit")
    column = _create_column(
        client,
        token=owner["token"],
        project_id=project["id"],
        tasks_limit=1,
    )

    first_response = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=column["id"],
    )
    assert first_response.status_code == 201, first_response.text

    second_response = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=column["id"],
    )

    assert second_response.status_code == 409, second_response.text
    _assert_error_code(second_response, "COLUMN_TASK_LIMIT_REACHED")


def test_create_task_rejects_column_from_another_project(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_wrong_column",
        email="owner_wrong_column@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Project A")
    other_project = _create_project(client, token=owner["token"], name="Project B")
    other_column = _create_column(
        client,
        token=owner["token"],
        project_id=other_project["id"],
    )

    response = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=other_column["id"],
    )

    assert response.status_code == 400, response.text
    _assert_error_code(response, "COLUMN_BELONGS_ANOTHER_PROJECT")
