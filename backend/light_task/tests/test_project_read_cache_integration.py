from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast
from uuid import uuid4

import redis
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import event
from sqlalchemy.engine import Connection

from src.config import settings
from src.db.database import db_helper
from tests.test_create_task_slice import (
    _add_member_via_invite,
    _auth_headers,
    _create_column,
    _create_project,
    _create_task,
    _register_and_login,
)


def _cache_keys(project_id: int) -> dict[str, str]:
    prefix = f"cache:v1:project:{project_id}"
    return {
        "board": f"{prefix}:board",
        "members": f"{prefix}:members",
        "tags": f"{prefix}:tags",
    }


def _get_project_reads(
    client: TestClient,
    *,
    token: str,
    project_id: int,
) -> dict[str, object]:
    headers = _auth_headers(token)
    paths = {
        "project": f"/api/projects/{project_id}",
        "board": f"/api/projects/{project_id}/columns",
        "members": f"/api/projects/{project_id}/members",
        "tags": f"/api/projects/{project_id}/tags",
    }
    payloads: dict[str, object] = {}
    for name, path in paths.items():
        response = client.get(path, headers=headers)
        assert response.status_code == 200, response.text
        payloads[name] = response.json()
    return payloads


@contextmanager
def _count_sql_statements() -> Iterator[list[str]]:
    statements: list[str] = []

    def record_statement(
        _connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    engine = db_helper.engine.sync_engine
    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)


def test_warm_project_reads_match_cold_json_and_execute_four_sql_queries(
    client: TestClient,
) -> None:
    owner = _register_and_login(
        client,
        username="owner_cache_warm",
        email="owner_cache_warm@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Cached Board")
    column = _create_column(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Todo",
    )
    task_response = cast(
        Response,
        _create_task(
            client,
            token=owner["token"],
            project_id=project["id"],
            column_id=column["id"],
            title="Cached task",
        ),
    )
    assert task_response.status_code == 201, task_response.text

    with _count_sql_statements() as cold_statements:
        cold = _get_project_reads(
            client,
            token=owner["token"],
            project_id=project["id"],
        )

    with _count_sql_statements() as statements:
        warm = _get_project_reads(
            client,
            token=owner["token"],
            project_id=project["id"],
        )

    assert warm == cold
    assert len(cold_statements) == 10, cold_statements
    assert len(statements) == 4, statements

    cache_client = redis.Redis.from_url(settings.cache.redis_url, decode_responses=True)
    try:
        for key in _cache_keys(project["id"]).values():
            assert cache_client.exists(key) == 1
            ttl = cast(int, cache_client.ttl(key))
            assert 0 < ttl <= settings.cache.ttl_seconds
    finally:
        cache_client.close()


def test_warm_cache_remains_inaccessible_to_non_member(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_cache_security",
        email="owner_cache_security@example.com",
    )
    outsider = _register_and_login(
        client,
        username="outsider_cache_security",
        email="outsider_cache_security@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Private Cache")
    _get_project_reads(
        client,
        token=owner["token"],
        project_id=project["id"],
    )

    for path in ("columns", "members", "tags"):
        response = client.get(
            f"/api/projects/{project['id']}/{path}",
            headers=_auth_headers(outsider["token"]),
        )
        assert response.status_code == 404
        assert response.json() == {"error": {"code": "PROJECT_NOT_FOUND"}}


def test_mutations_invalidate_only_the_affected_project_caches(
    client: TestClient,
) -> None:
    owner = _register_and_login(
        client,
        username="owner_cache_invalidation",
        email="owner_cache_invalidation@example.com",
    )
    member = _register_and_login(
        client,
        username="member_cache_invalidation",
        email="member_cache_invalidation@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Invalidations")
    column = _create_column(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Todo",
    )
    keys = _cache_keys(project["id"])
    cache_client = redis.Redis.from_url(settings.cache.redis_url, decode_responses=True)

    try:
        _get_project_reads(
            client,
            token=owner["token"],
            project_id=project["id"],
        )
        task_response = cast(
            Response,
            _create_task(
                client,
                token=owner["token"],
                project_id=project["id"],
                column_id=column["id"],
                title="Invalidates board",
            ),
        )
        assert task_response.status_code == 201, task_response.text
        assert cache_client.exists(keys["board"]) == 0
        assert cache_client.exists(keys["members"]) == 1
        assert cache_client.exists(keys["tags"]) == 1

        _get_project_reads(
            client,
            token=owner["token"],
            project_id=project["id"],
        )
        tags = client.get(
            f"/api/projects/{project['id']}/tags",
            headers=_auth_headers(owner["token"]),
        ).json()
        tag_response = client.patch(
            f"/api/tags/{tags[0]['id']}",
            json={"name": "Updated default tag"},
            headers=_auth_headers(owner["token"], str(uuid4())),
        )
        assert tag_response.status_code == 200, tag_response.text
        assert cache_client.exists(keys["board"]) == 0
        assert cache_client.exists(keys["members"]) == 1
        assert cache_client.exists(keys["tags"]) == 0

        _get_project_reads(
            client,
            token=owner["token"],
            project_id=project["id"],
        )
        _add_member_via_invite(
            client,
            owner_token=owner["token"],
            member_token=member["token"],
            project_id=project["id"],
        )
        assert cache_client.exists(keys["board"]) == 1
        assert cache_client.exists(keys["members"]) == 0
        assert cache_client.exists(keys["tags"]) == 1

        _get_project_reads(
            client,
            token=owner["token"],
            project_id=project["id"],
        )
        role_response = client.patch(
            f"/api/projects/{project['id']}/members/{member['user']['id']}",
            json={"role": "MANAGER"},
            headers=_auth_headers(owner["token"], str(uuid4())),
        )
        assert role_response.status_code == 200, role_response.text
        assert role_response.json()["role"] == "MANAGER"
        assert cache_client.exists(keys["members"]) == 0

        members_response = client.get(
            f"/api/projects/{project['id']}/members",
            headers=_auth_headers(owner["token"]),
        )
        assert members_response.status_code == 200, members_response.text
        member_payload = next(
            item for item in members_response.json() if item["user"]["id"] == member["user"]["id"]
        )
        assert member_payload["role"] == "MANAGER"

        _get_project_reads(
            client,
            token=member["token"],
            project_id=project["id"],
        )
        remove_response = client.delete(
            f"/api/projects/{project['id']}/members/{member['user']['id']}",
            headers=_auth_headers(owner["token"], str(uuid4())),
        )
        assert remove_response.status_code == 204, remove_response.text
        assert cache_client.exists(keys["members"]) == 0

        for path in ("columns", "members", "tags"):
            denied_response = client.get(
                f"/api/projects/{project['id']}/{path}",
                headers=_auth_headers(member["token"]),
            )
            assert denied_response.status_code == 404
            assert denied_response.json() == {"error": {"code": "PROJECT_NOT_FOUND"}}

        _get_project_reads(
            client,
            token=owner["token"],
            project_id=project["id"],
        )
        delete_response = client.delete(
            f"/api/projects/{project['id']}",
            headers=_auth_headers(owner["token"], str(uuid4())),
        )
        assert delete_response.status_code == 204, delete_response.text
        assert all(cache_client.exists(key) == 0 for key in keys.values())
    finally:
        cache_client.close()
