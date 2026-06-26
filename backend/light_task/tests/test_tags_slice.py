from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from test_create_task_slice import (
    _add_member_via_invite,
    _auth_headers,
    _create_project,
    _promote_member_to_manager,
    _register_and_login,
)
from test_realtime_integration import _auth_project_ws, _receive_event

from src.realtimev1.events import RealtimeEventType


def _create_tag(
    client: TestClient,
    *,
    token: str,
    project_id: int,
    name: str = "Backend",
    color: str = "#9CA3AF",
    client_mutation_id: str | None = None,
):
    return client.post(
        f"/api/projects/{project_id}/tags",
        json={"name": name, "color": color},
        headers=_auth_headers(token, client_mutation_id or str(uuid4())),
    )


def _update_tag(
    client: TestClient,
    *,
    token: str,
    tag_id: int,
    payload: dict,
    client_mutation_id: str | None = None,
):
    return client.patch(
        f"/api/tags/{tag_id}",
        json=payload,
        headers=_auth_headers(token, client_mutation_id or str(uuid4())),
    )


def _delete_tag(
    client: TestClient,
    *,
    token: str,
    tag_id: int,
    client_mutation_id: str | None = None,
):
    return client.delete(
        f"/api/tags/{tag_id}",
        headers=_auth_headers(token, client_mutation_id or str(uuid4())),
    )


def _assert_error_code(response, expected_code: str) -> None:
    assert response.json() == {"error": {"code": expected_code}}


def test_owner_can_create_tag_with_unchanged_response_shape(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_tag_create",
        email="owner_tag_create@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Tag Create")

    response = _create_tag(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Backend",
        color="#22C55E",
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["id"] > 0
    assert payload["projectId"] == project["id"]
    assert payload["name"] == "Backend"
    assert payload["color"] == "#22C55E"


def test_member_cannot_create_tag(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_tag_member_denied",
        email="owner_tag_member_denied@example.com",
    )
    member = _register_and_login(
        client,
        username="member_tag_denied",
        email="member_tag_denied@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Tag Member Denied")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )

    response = _create_tag(
        client,
        token=member["token"],
        project_id=project["id"],
    )

    assert response.status_code == 403, response.text
    _assert_error_code(response, "INSUFFICIENT_PERMISSIONS")


def test_manager_can_update_tag(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_tag_manager_update",
        email="owner_tag_manager_update@example.com",
    )
    manager = _register_and_login(
        client,
        username="manager_tag_update",
        email="manager_tag_update@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Tag Manager")
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
    tag = _create_tag(
        client,
        token=owner["token"],
        project_id=project["id"],
    ).json()

    response = _update_tag(
        client,
        token=manager["token"],
        tag_id=tag["id"],
        payload={"name": "Frontend", "color": "#EF4444"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Frontend"
    assert response.json()["color"] == "#EF4444"


def test_update_tag_duplicate_name_returns_tag_already_exists(
    client: TestClient,
) -> None:
    owner = _register_and_login(
        client,
        username="owner_tag_duplicate",
        email="owner_tag_duplicate@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Tag Duplicate")
    first_tag = _create_tag(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Backend",
    ).json()
    _create_tag(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Frontend",
    )

    response = _update_tag(
        client,
        token=owner["token"],
        tag_id=first_tag["id"],
        payload={"name": "Frontend"},
    )

    assert response.status_code == 409, response.text
    _assert_error_code(response, "TAG_ALREADY_EXISTS")


def test_delete_tag_not_found(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_tag_missing",
        email="owner_tag_missing@example.com",
    )

    response = _delete_tag(
        client,
        token=owner["token"],
        tag_id=999999,
    )

    assert response.status_code == 404, response.text
    _assert_error_code(response, "TAG_NOT_FOUND")


def test_member_cannot_delete_tag(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_tag_member_delete",
        email="owner_tag_member_delete@example.com",
    )
    member = _register_and_login(
        client,
        username="member_tag_delete",
        email="member_tag_delete@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Tag Delete Denied")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )
    tag = _create_tag(
        client,
        token=owner["token"],
        project_id=project["id"],
    ).json()

    response = _delete_tag(
        client,
        token=member["token"],
        tag_id=tag["id"],
    )

    assert response.status_code == 403, response.text
    _assert_error_code(response, "INSUFFICIENT_PERMISSIONS")


def test_tag_realtime_contracts(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_tag_realtime",
        email="owner_tag_realtime@example.com",
    )
    manager = _register_and_login(
        client,
        username="manager_tag_realtime",
        email="manager_tag_realtime@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Tag Realtime")
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

    with _auth_project_ws(
        client,
        token=manager["token"],
        project_id=project["id"],
    ) as ws_manager:
        create_mutation = f"tag-create-{uuid4()}"
        create_response = _create_tag(
            client,
            token=owner["token"],
            project_id=project["id"],
            name="Realtime",
            client_mutation_id=create_mutation,
        )
        assert create_response.status_code == 201, create_response.text
        tag = create_response.json()

        created_event = _receive_event(ws_manager, RealtimeEventType.TAG_CREATED)
        assert created_event["payload"]["tag"]["id"] == tag["id"]
        assert created_event["payload"]["tag"]["name"] == "Realtime"
        assert created_event["clientMutationId"] == create_mutation

        update_mutation = f"tag-update-{uuid4()}"
        update_response = _update_tag(
            client,
            token=owner["token"],
            tag_id=tag["id"],
            payload={"name": "Realtime Updated"},
            client_mutation_id=update_mutation,
        )
        assert update_response.status_code == 200, update_response.text

        updated_event = _receive_event(ws_manager, RealtimeEventType.TAG_UPDATED)
        assert updated_event["payload"]["tag"]["id"] == tag["id"]
        assert updated_event["payload"]["tag"]["name"] == "Realtime Updated"
        assert updated_event["clientMutationId"] == update_mutation

        delete_mutation = f"tag-delete-{uuid4()}"
        delete_response = _delete_tag(
            client,
            token=owner["token"],
            tag_id=tag["id"],
            client_mutation_id=delete_mutation,
        )
        assert delete_response.status_code == 204, delete_response.text

        deleted_event = _receive_event(ws_manager, RealtimeEventType.TAG_DELETED)
        assert deleted_event["payload"]["tagId"] == tag["id"]
        assert deleted_event["clientMutationId"] == delete_mutation
