from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from test_create_task_slice import (
    _add_member_via_invite,
    _auth_headers,
    _create_column,
    _create_project,
    _create_task,
    _promote_member_to_manager,
    _register_and_login,
)


def _move_task(
    client: TestClient,
    *,
    token: str,
    task_id: int,
    new_column_id: int,
    after_task_id: int | None = None,
):
    return client.patch(
        f"/api/tasks/{task_id}/move",
        json={"newColumnId": new_column_id, "afterTaskId": after_task_id},
        headers=_auth_headers(token, str(uuid4())),
    )


def _assert_error_code(response, expected_code: str) -> None:
    assert response.json() == {"error": {"code": expected_code}}


def test_owner_can_move_task_with_unchanged_response_shape(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_move_task",
        email="owner_move_task@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Move Task")
    source_column = _create_column(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Todo",
    )
    target_column = _create_column(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Done",
    )
    task = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=source_column["id"],
    ).json()

    response = _move_task(
        client,
        token=owner["token"],
        task_id=task["id"],
        new_column_id=target_column["id"],
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == task["id"]
    assert payload["columnId"] == target_column["id"]
    assert isinstance(payload["position"], float)
    assert isinstance(payload["updatedAt"], str)


def test_manager_can_move_task(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_manager_move",
        email="owner_manager_move@example.com",
    )
    manager = _register_and_login(
        client,
        username="manager_move",
        email="manager_move@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Manager Move")
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
    source_column = _create_column(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Todo",
    )
    target_column = _create_column(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Done",
    )
    task = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=source_column["id"],
    ).json()

    response = _move_task(
        client,
        token=manager["token"],
        task_id=task["id"],
        new_column_id=target_column["id"],
    )

    assert response.status_code == 200, response.text


def test_member_can_move_task_assigned_to_self(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_member_move_self",
        email="owner_member_move_self@example.com",
    )
    member = _register_and_login(
        client,
        username="member_move_self",
        email="member_move_self@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Member Move Self")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )
    source_column = _create_column(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Todo",
    )
    target_column = _create_column(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Done",
    )
    task = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=source_column["id"],
        assignee_id=member["user"]["id"],
    ).json()

    response = _move_task(
        client,
        token=member["token"],
        task_id=task["id"],
        new_column_id=target_column["id"],
    )

    assert response.status_code == 200, response.text


def test_member_cannot_move_task_assigned_to_another_user(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_member_move_other",
        email="owner_member_move_other@example.com",
    )
    member = _register_and_login(
        client,
        username="member_move_other",
        email="member_move_other@example.com",
    )
    other_member = _register_and_login(
        client,
        username="other_move_member",
        email="other_move_member@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Member Move Other")
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
    source_column = _create_column(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Todo",
    )
    target_column = _create_column(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Done",
    )
    task = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=source_column["id"],
        assignee_id=other_member["user"]["id"],
    ).json()

    response = _move_task(
        client,
        token=member["token"],
        task_id=task["id"],
        new_column_id=target_column["id"],
    )

    assert response.status_code == 403, response.text
    _assert_error_code(response, "MEMBERS_ONLY_OWN_TASKS")


def test_move_task_rejects_invalid_target_column(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_invalid_target",
        email="owner_invalid_target@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Move Project A")
    other_project = _create_project(
        client,
        token=owner["token"],
        name="Move Project B",
    )
    source_column = _create_column(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Todo",
    )
    other_column = _create_column(
        client,
        token=owner["token"],
        project_id=other_project["id"],
        name="Elsewhere",
    )
    task = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=source_column["id"],
    ).json()

    response = _move_task(
        client,
        token=owner["token"],
        task_id=task["id"],
        new_column_id=other_column["id"],
    )

    assert response.status_code == 400, response.text
    _assert_error_code(response, "INVALID_TARGET_COLUMN")


def test_move_task_rejects_missing_anchor_task(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_missing_anchor",
        email="owner_missing_anchor@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Missing Anchor")
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
    ).json()

    response = _move_task(
        client,
        token=owner["token"],
        task_id=task["id"],
        new_column_id=column["id"],
        after_task_id=999999,
    )

    assert response.status_code == 409, response.text
    _assert_error_code(response, "ANCHOR_TASK_NOT_FOUND")


def test_move_task_respects_target_column_task_limit(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_move_limit",
        email="owner_move_limit@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Move Limit")
    source_column = _create_column(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Todo",
    )
    target_column = _create_column(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Full",
        tasks_limit=1,
    )
    existing_target_task = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=target_column["id"],
    )
    assert existing_target_task.status_code == 201, existing_target_task.text
    task_to_move = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=source_column["id"],
    ).json()

    response = _move_task(
        client,
        token=owner["token"],
        task_id=task_to_move["id"],
        new_column_id=target_column["id"],
    )

    assert response.status_code == 409, response.text
    _assert_error_code(response, "COLUMN_TASK_LIMIT_REACHED")
