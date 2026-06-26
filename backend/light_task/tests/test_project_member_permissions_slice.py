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


def _update_member_role(
    client: TestClient,
    *,
    token: str,
    project_id: int,
    user_id: int,
    role: str,
    client_mutation_id: str | None = None,
):
    return client.patch(
        f"/api/projects/{project_id}/members/{user_id}",
        json={"role": role},
        headers=_auth_headers(token, client_mutation_id or str(uuid4())),
    )


def _remove_member(
    client: TestClient,
    *,
    token: str,
    project_id: int,
    user_id: int,
    client_mutation_id: str | None = None,
):
    return client.delete(
        f"/api/projects/{project_id}/members/{user_id}",
        headers=_auth_headers(token, client_mutation_id or str(uuid4())),
    )


def _assert_error_code(response, expected_code: str) -> None:
    assert response.json() == {"error": {"code": expected_code}}


def test_owner_can_update_member_role_with_unchanged_response_shape(
    client: TestClient,
) -> None:
    owner = _register_and_login(
        client,
        username="owner_role_update",
        email="owner_role_update@example.com",
    )
    member = _register_and_login(
        client,
        username="member_role_update",
        email="member_role_update@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Role Update")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )

    response = _update_member_role(
        client,
        token=owner["token"],
        project_id=project["id"],
        user_id=member["user"]["id"],
        role="MANAGER",
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] > 0
    assert payload["role"] == "MANAGER"
    assert payload["user"]["id"] == member["user"]["id"]
    assert isinstance(payload["joinedAt"], str)


def test_manager_cannot_update_member_role(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_manager_role_denied",
        email="owner_manager_role_denied@example.com",
    )
    manager = _register_and_login(
        client,
        username="manager_role_denied",
        email="manager_role_denied@example.com",
    )
    member = _register_and_login(
        client,
        username="member_role_denied",
        email="member_role_denied@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Manager Denied")
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
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )

    response = _update_member_role(
        client,
        token=manager["token"],
        project_id=project["id"],
        user_id=member["user"]["id"],
        role="MANAGER",
    )

    assert response.status_code == 403, response.text
    _assert_error_code(response, "INSUFFICIENT_PERMISSIONS")


def test_owner_role_cannot_be_changed(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_role_unchanged",
        email="owner_role_unchanged@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Owner Role")

    response = _update_member_role(
        client,
        token=owner["token"],
        project_id=project["id"],
        user_id=owner["user"]["id"],
        role="MEMBER",
    )

    assert response.status_code == 400, response.text
    _assert_error_code(response, "CANNOT_CHANGE_OWNER_ROLE")


def test_owner_can_remove_member(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_remove_member",
        email="owner_remove_member@example.com",
    )
    member = _register_and_login(
        client,
        username="member_removed",
        email="member_removed@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Remove Member")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )

    response = _remove_member(
        client,
        token=owner["token"],
        project_id=project["id"],
        user_id=member["user"]["id"],
    )

    assert response.status_code == 204, response.text
    assert response.content == b""


def test_member_cannot_remove_member(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_member_remove_denied",
        email="owner_member_remove_denied@example.com",
    )
    member = _register_and_login(
        client,
        username="member_remove_denied",
        email="member_remove_denied@example.com",
    )
    other = _register_and_login(
        client,
        username="other_remove_denied",
        email="other_remove_denied@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Member Denied")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=other["token"],
        project_id=project["id"],
    )

    response = _remove_member(
        client,
        token=member["token"],
        project_id=project["id"],
        user_id=other["user"]["id"],
    )

    assert response.status_code == 403, response.text
    _assert_error_code(response, "INSUFFICIENT_PERMISSIONS")


def test_manager_cannot_remove_manager(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_manager_remove_manager",
        email="owner_manager_remove_manager@example.com",
    )
    manager = _register_and_login(
        client,
        username="manager_remove_manager",
        email="manager_remove_manager@example.com",
    )
    other_manager = _register_and_login(
        client,
        username="other_manager_remove",
        email="other_manager_remove@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Manager Remove")
    for user in [manager, other_manager]:
        _add_member_via_invite(
            client,
            owner_token=owner["token"],
            member_token=user["token"],
            project_id=project["id"],
        )
        _promote_member_to_manager(
            client,
            owner_token=owner["token"],
            project_id=project["id"],
            user_id=user["user"]["id"],
        )

    response = _remove_member(
        client,
        token=manager["token"],
        project_id=project["id"],
        user_id=other_manager["user"]["id"],
    )

    assert response.status_code == 403, response.text
    _assert_error_code(response, "MANAGERS_CANNOT_REMOVE")


def test_owner_cannot_be_removed(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_cannot_remove",
        email="owner_cannot_remove@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Cannot Remove Owner")

    response = _remove_member(
        client,
        token=owner["token"],
        project_id=project["id"],
        user_id=owner["user"]["id"],
    )

    assert response.status_code == 403, response.text
    _assert_error_code(response, "CANNOT_REMOVE_OWNER")


def test_member_role_changed_realtime_contract(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_role_realtime",
        email="owner_role_realtime@example.com",
    )
    member = _register_and_login(
        client,
        username="member_role_realtime",
        email="member_role_realtime@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Role Realtime")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )

    with _auth_project_ws(
        client,
        token=member["token"],
        project_id=project["id"],
    ) as ws_member:
        mutation_id = f"member-role-{uuid4()}"
        response = _update_member_role(
            client,
            token=owner["token"],
            project_id=project["id"],
            user_id=member["user"]["id"],
            role="MANAGER",
            client_mutation_id=mutation_id,
        )
        assert response.status_code == 200, response.text

        event = _receive_event(ws_member, RealtimeEventType.MEMBER_ROLE_CHANGED)
        assert event["payload"]["userId"] == member["user"]["id"]
        assert event["payload"]["role"] == "MANAGER"
        assert event["payload"]["previousRole"] == "MEMBER"
        assert event["clientMutationId"] == mutation_id
