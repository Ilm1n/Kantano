from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import generate_latest
from prometheus_client.parser import text_string_to_metric_families
from starlette.responses import Response

from src.observability.metrics import (
    ApplicationMetrics,
    record_cache_operation,
    set_active_metrics,
)
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

    @app.get("/status/{code}")
    async def status(code: int) -> Response:
        return Response(status_code=code)

    application_metrics = ApplicationMetrics()
    application_metrics.instrument_fastapi(app)

    with TestClient(RequestContextMiddleware(app)) as client:
        assert client.get("/items/101").json() == {"item_id": 101}
        assert client.get("/items/202").json() == {"item_id": 202}
        assert client.get("/unknown/303").status_code == 404
        assert client.get("/api/health").status_code == 200
        for code in (201, 204, 302, 400, 401, 422, 500, 503):
            assert client.get(f"/status/{code}", follow_redirects=False).status_code == code
        exposition = client.get("/metrics").text

    samples = [s for family in text_string_to_metric_families(exposition) for s in family.samples]
    requests = [s for s in samples if s.name == "http_requests_total"]
    assert all(set(s.labels) == {"status"} for s in requests)
    assert {s.labels["status"]: s.value for s in requests} == {
        "2xx": 4,
        "3xx": 1,
        "4xx": 4,
        "5xx": 2,
    }
    buckets = [s for s in samples if s.name == "http_request_duration_seconds_bucket"]
    assert all(set(s.labels) == {"handler", "le"} for s in buckets)
    assert {s.labels["handler"] for s in buckets} == {"/items/{item_id}", "/status/{code}", "none"}
    assert {float(s.labels["le"]) for s in buckets} == {
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1,
        2.5,
        5,
        10,
        float("inf"),
    }
    assert sum(s.value for s in buckets if s.labels["le"] == "+Inf") == 11
    assert all(s.labels == {} for s in samples if s.name == "http_requests_inprogress")
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


def test_cache_metrics_use_bounded_cache_operation_and_result_labels() -> None:
    application_metrics = ApplicationMetrics()
    set_active_metrics(application_metrics)
    try:
        record_cache_operation("project_board", "get", "hit")
        record_cache_operation("project_tags", "set", "oversized")
    finally:
        set_active_metrics(None)

    exposition = generate_latest(application_metrics.registry).decode()
    assert (
        'kantano_cache_operations_total{cache="project_board",operation="get",result="hit"} 1.0'
    ) in exposition
    assert (
        'kantano_cache_operations_total{cache="project_tags",operation="set",result="oversized"} '
        "1.0"
    ) in exposition
