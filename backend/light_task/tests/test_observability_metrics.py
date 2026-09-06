from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import generate_latest

from src.observability.metrics import ApplicationMetrics
from src.observability.middleware import RequestContextMiddleware

pytestmark = pytest.mark.no_infra


def test_http_metrics_use_route_templates_status_and_expected_buckets() -> None:
    app = FastAPI()

    @app.get("/items/{item_id}")
    async def item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    application_metrics = ApplicationMetrics()
    application_metrics.instrument_fastapi(app)

    with TestClient(RequestContextMiddleware(app)) as client:
        assert client.get("/items/101").json() == {"item_id": 101}
        assert client.get("/items/202").json() == {"item_id": 202}
        assert client.get("/unknown/303").status_code == 404
        assert client.get("/api/health").status_code == 200
        exposition = client.get("/metrics").text

    assert 'handler="/items/{item_id}",method="GET",status="200"' in exposition
    assert 'handler="none",method="GET",status="404"' in exposition
    assert "/items/101" not in exposition
    assert "/items/202" not in exposition
    assert "/unknown/303" not in exposition
    assert 'handler="/api/health"' not in exposition
    assert 'le="0.005"' in exposition
    assert 'le="10.0"' in exposition
    assert "http_requests_inprogress" in exposition


def test_outbox_metrics_keep_unknown_age_distinct_from_zero_backlog() -> None:
    application_metrics = ApplicationMetrics()

    application_metrics.update_outbox_stats(count=3, oldest_timestamp=1_700_000_000.0)
    first = generate_latest(application_metrics.registry).decode()
    assert "kantano_outbox_unpublished_events 3.0" in first
    assert "kantano_outbox_oldest_created_timestamp_seconds 1.7e+09" in first

    application_metrics.update_outbox_stats(count=0, oldest_timestamp=None)
    second = generate_latest(application_metrics.registry).decode()
    assert "kantano_outbox_unpublished_events 0.0" in second
    assert "kantano_outbox_oldest_created_timestamp_seconds 0.0" in second
    assert "kantano_outbox_stats_last_update_timestamp_seconds" in second


def test_metric_registration_supports_isolated_registries() -> None:
    first = ApplicationMetrics()
    second = ApplicationMetrics()

    first.record_outbox_publish("success")
    second.record_outbox_publish("failure")

    first_text = generate_latest(first.registry).decode()
    second_text = generate_latest(second.registry).decode()
    assert 'kantano_outbox_publish_total{result="success"} 1.0' in first_text
    assert 'result="failure"' not in first_text
    assert 'kantano_outbox_publish_total{result="failure"} 1.0' in second_text
    assert 'result="success"' not in second_text
