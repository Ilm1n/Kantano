from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from test_create_task_slice import (
    _add_member_via_invite,
    _auth_headers,
    _create_column,
    _create_project,
    _create_tag,
    _create_task,
    _promote_member_to_manager,
    _register_and_login,
)
from test_realtime_integration import _auth_project_ws, _receive_event

from src.realtimev1.events import RealtimeEventType


def _update_task(
    client: TestClient,
    *,
    token: str,
    task_id: int,
    payload: dict,
    client_mutation_id: str | None = None,
):
    return client.patch(
        f"/api/tasks/{task_id}",
        json=payload,
        headers=_auth_headers(token, client_mutation_id or str(uuid4())),
    )


def _delete_task(
    client: TestClient,
    *,
    token: str,
    task_id: int,
    client_mutation_id: str | None = None,
):
    return client.delete(
        f"/api/tasks/{task_id}",
        headers=_auth_headers(token, client_mutation_id or str(uuid4())),
    )


def _assert_error_code(response, expected_code: str) -> None:
    assert response.json() == {"error": {"code": expected_code}}


def test_owner_can_update_task_with_unchanged_response_shape(
    client: TestClient,
) -> None:
    owner = _register_and_login(
        client,
        username="owner_update_task",
        email="owner_update_task@example.com",
    )
    member = _register_and_login(
        client,
        username="assignee_update_task",
        email="assignee_update_task@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Update Task")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )
    column = _create_column(client, token=owner["token"], project_id=project["id"])
    tag = _create_tag(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Updated",
    )
    task = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=column["id"],
    ).json()

    response = _update_task(
        client,
        token=owner["token"],
        task_id=task["id"],
        payload={
            "title": "Updated title",
            "description": "Updated description",
            "priority": "HIGH",
            "assigneeId": member["user"]["id"],
            "tagIds": [tag["id"]],
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == task["id"]
    assert payload["title"] == "Updated title"
    assert payload["description"] == "Updated description"
    assert payload["priority"] == "HIGH"
    assert payload["assigneeId"] == member["user"]["id"]
    assert payload["tags"] == [tag]
    assert payload["projectId"] == project["id"]
    assert payload["columnId"] == column["id"]
    assert isinstance(payload["position"], float)
    assert isinstance(payload["createdAt"], str)
    assert isinstance(payload["updatedAt"], str)


def test_member_can_update_task_assigned_to_self(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_member_update_self",
        email="owner_member_update_self@example.com",
    )
    member = _register_and_login(
        client,
        username="member_update_self",
        email="member_update_self@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Member Update Self")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )
    column = _create_column(client, token=owner["token"], project_id=project["id"])
    task = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=column["id"],
        assignee_id=member["user"]["id"],
    ).json()

    response = _update_task(
        client,
        token=member["token"],
        task_id=task["id"],
        payload={"title": "Member updated"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Member updated"


def test_member_cannot_update_task_assigned_to_another_user(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_member_update_other",
        email="owner_member_update_other@example.com",
    )
    member = _register_and_login(
        client,
        username="member_update_other",
        email="member_update_other@example.com",
    )
    other_member = _register_and_login(
        client,
        username="other_update_member",
        email="other_update_member@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Member Update Other")
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
    task = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=column["id"],
        assignee_id=other_member["user"]["id"],
    ).json()

    response = _update_task(
        client,
        token=member["token"],
        task_id=task["id"],
        payload={"title": "Nope"},
    )

    assert response.status_code == 403, response.text
    _assert_error_code(response, "MEMBERS_ONLY_OWN_TASKS")


def test_update_task_rejects_assignee_outside_project(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_update_assignee_outside",
        email="owner_update_assignee_outside@example.com",
    )
    outsider = _register_and_login(
        client,
        username="outsider_update_assignee",
        email="outsider_update_assignee@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Update Assignee")
    column = _create_column(client, token=owner["token"], project_id=project["id"])
    task = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=column["id"],
    ).json()

    response = _update_task(
        client,
        token=owner["token"],
        task_id=task["id"],
        payload={"assigneeId": outsider["user"]["id"]},
    )

    assert response.status_code == 400, response.text
    _assert_error_code(response, "ASSIGNEE_NOT_PROJECT_MEMBER")


def test_update_task_rejects_invalid_tag_ids(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_update_invalid_tags",
        email="owner_update_invalid_tags@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Invalid Update Tags")
    column = _create_column(client, token=owner["token"], project_id=project["id"])
    task = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=column["id"],
    ).json()

    response = _update_task(
        client,
        token=owner["token"],
        task_id=task["id"],
        payload={"tagIds": [999999]},
    )

    assert response.status_code == 400, response.text
    _assert_error_code(response, "INVALID_TAG_IDS")


def test_manager_can_delete_task(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_manager_delete_task",
        email="owner_manager_delete_task@example.com",
    )
    manager = _register_and_login(
        client,
        username="manager_delete_task",
        email="manager_delete_task@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Manager Delete")
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
    task = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=column["id"],
    ).json()

    response = _delete_task(
        client,
        token=manager["token"],
        task_id=task["id"],
    )

    assert response.status_code == 204, response.text
    assert response.content == b""


def test_member_cannot_delete_task(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_member_delete_task",
        email="owner_member_delete_task@example.com",
    )
    member = _register_and_login(
        client,
        username="member_delete_task",
        email="member_delete_task@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Member Delete")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )
    column = _create_column(client, token=owner["token"], project_id=project["id"])
    task = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=column["id"],
        assignee_id=member["user"]["id"],
    ).json()

    response = _delete_task(
        client,
        token=member["token"],
        task_id=task["id"],
    )

    assert response.status_code == 403, response.text
    _assert_error_code(response, "INSUFFICIENT_PERMISSIONS")


def test_task_updated_realtime_event_contract(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_update_realtime",
        email="owner_update_realtime@example.com",
    )
    member = _register_and_login(
        client,
        username="member_update_realtime",
        email="member_update_realtime@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Update Realtime")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )
    column = _create_column(client, token=owner["token"], project_id=project["id"])
    task = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=column["id"],
    ).json()

    with _auth_project_ws(
        client,
        token=member["token"],
        project_id=project["id"],
    ) as ws_member:
        mutation_id = f"task-update-{uuid4()}"
        response = _update_task(
            client,
            token=owner["token"],
            task_id=task["id"],
            payload={"title": "Realtime updated"},
            client_mutation_id=mutation_id,
        )
        assert response.status_code == 200, response.text

        event = _receive_event(ws_member, RealtimeEventType.TASK_UPDATED)
        assert event["payload"]["task"]["id"] == task["id"]
        assert event["payload"]["task"]["title"] == "Realtime updated"
        assert event["clientMutationId"] == mutation_id


def test_task_deleted_realtime_event_contract(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_delete_realtime",
        email="owner_delete_realtime@example.com",
    )
    member = _register_and_login(
        client,
        username="member_delete_realtime",
        email="member_delete_realtime@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Delete Realtime")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )
    column = _create_column(client, token=owner["token"], project_id=project["id"])
    task = _create_task(
        client,
        token=owner["token"],
        project_id=project["id"],
        column_id=column["id"],
    ).json()

    with _auth_project_ws(
        client,
        token=member["token"],
        project_id=project["id"],
    ) as ws_member:
        mutation_id = f"task-delete-{uuid4()}"
        response = _delete_task(
            client,
            token=owner["token"],
            task_id=task["id"],
            client_mutation_id=mutation_id,
        )
        assert response.status_code == 204, response.text

        event = _receive_event(ws_member, RealtimeEventType.TASK_DELETED)
        assert event["payload"]["taskId"] == task["id"]
        assert event["payload"]["columnId"] == column["id"]
        assert event["clientMutationId"] == mutation_id
