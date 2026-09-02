from typing import NoReturn

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine


def test_liveness_returns_ok_without_database_query(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_returns_ok_when_database_is_available(client: TestClient) -> None:
    response = client.get("/api/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_returns_service_unavailable_when_database_is_down(
    client: TestClient,
    monkeypatch,
) -> None:
    def unavailable_connection(_: AsyncEngine) -> NoReturn:
        raise OperationalError("SELECT 1", {}, RuntimeError("database is unavailable"))

    monkeypatch.setattr(AsyncEngine, "connect", unavailable_connection)

    response = client.get("/api/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
