from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.validate_observability import (
    ROOT,
    Query,
    allowlist,
    inventory,
    metrics,
    production_filter,
    validate,
    validate_labels,
)

pytestmark = pytest.mark.no_infra


def test_dashboards_and_alerts_match_production_allowlist() -> None:
    assert validate()


@pytest.mark.parametrize(
    "expression",
    [
        'rate(new_metric_total{status="5xx"}[5m])',
        "sum by (handler) (rate(new_metric_total[5m]))",
        "sum(rate(new_metric_total[5m])) / sum(old_metric)",
    ],
)
def test_new_metric_is_extracted(expression: str) -> None:
    assert "new_metric_total" in metrics(expression)


@pytest.mark.parametrize(
    "expression",
    [
        "sum(broken",
        '{__name__=~"pg_.*"}',
        '{job="api"}',
        '{__name__!="up"}',
    ],
)
def test_unparseable_or_open_ended_metric_queries_fail(expression: str) -> None:
    with pytest.raises(ValueError):
        metrics(expression)


def test_finite_name_selector_and_external_datasource(tmp_path: Path) -> None:
    assert metrics('{__name__=~"pg_up|redis_up"}') == {"pg_up", "redis_up"}
    directory = tmp_path / "observability/grafana"
    (directory / "dashboards").mkdir(parents=True)
    alerts = directory / "alert-rules.json"
    alerts.write_text('[{"expr":"grafanacloud_org_logs_usage","datasource":"usage"}]')
    assert inventory(tmp_path)[0] == set()
    alerts.write_text('[{"expr":"grafanacloud_org_logs_usage"}]')
    with pytest.raises(ValueError, match="usage datasource"):
        inventory(tmp_path)
    alerts.write_text('[{"expr":"grafanacloud_unknown","datasource":"usage"}]')
    with pytest.raises(ValueError, match="Unknown external"):
        inventory(tmp_path)


def test_cpu_root_filesystem_and_known_target_health() -> None:
    for mode in ("idle", "user", "system", "iowait", "irq", "steal", ""):
        result = production_filter(
            {"__name__": "node_cpu_seconds_total", "job": "integrations/unix", "mode": mode}
        )
        assert (result is not None) == (mode == "idle")
    for device in ("/dev/vda1", "/dev/sda2", "/dev/nvme0n1p1"):
        for mountpoint, fstype, kept in (
            ("/", "ext4", True),
            ("/", "xfs", True),
            ("/", "overlay", False),
            ("/run", "tmpfs", False),
            ("/var/lib/docker/overlay2/abc", "ext4", False),
        ):
            result = production_filter(
                {
                    "__name__": "node_filesystem_avail_bytes",
                    "job": "integrations/unix",
                    "device": device,
                    "fstype": fstype,
                    "mountpoint": mountpoint,
                }
            )
            assert (result is not None) == kept
    for job in (
        "kantano-api",
        "kantano-outbox-publisher",
        "kantano-celery-worker",
        "integrations/unix",
        "integrations/postgres",
        "integrations/redis",
        "integrations/cadvisor",
        "rabbitmq",
        "alloy",
    ):
        assert production_filter({"__name__": "up", "job": job}) is not None
    assert production_filter({"__name__": "up", "job": "unknown"}) is None


def test_compose_recreate_identity_and_no_duplicate_labelsets() -> None:
    results = []
    for container_id in ("old-id", "new-id"):
        for cpu in ("cpu00", "cpu01", "total"):
            result = production_filter(
                {
                    "__name__": "container_cpu_usage_seconds_total",
                    "job": "integrations/cadvisor",
                    "id": container_id,
                    "cpu": cpu,
                    "name": f"lighttask_prod-backend-{container_id}",
                    "container_label_com_docker_compose_project": "lighttask_prod",
                    "container_label_com_docker_compose_service": "backend",
                    "container_label_com_docker_compose_container_number": "1",
                }
            )
            assert result is not None
            assert "name" not in result and "image" not in result
            assert "id" in result and "cpu" in result
            results.append(tuple(sorted(result.items())))
    assert len(results) == len(set(results))
    for project, service in (("unrelated", "backend"), ("lighttask_prod", "migrations"), ("", "")):
        assert (
            production_filter(
                {
                    "__name__": "container_memory_working_set_bytes",
                    "job": "integrations/cadvisor",
                    "container_label_com_docker_compose_project": project,
                    "container_label_com_docker_compose_service": service,
                }
            )
            is None
        )


def test_unused_exporter_families_are_dropped() -> None:
    assert (
        production_filter(
            {"__name__": "pg_settings_max_connections", "job": "integrations/postgres"}
        )
        is None
    )
    config = (ROOT / "observability/alloy/config.prod.alloy").read_text()
    assert "http_request_duration_seconds_sum" not in allowlist(config)


def test_cache_and_redis_memory_metrics_reach_production() -> None:
    assert (
        production_filter({"__name__": "kantano_cache_operations_total", "job": "kantano-api"})
        is not None
    )
    assert (
        production_filter(
            {"__name__": "kantano_cache_operations_total", "job": "kantano-celery-worker"}
        )
        is None
    )
    assert (
        production_filter({"__name__": "redis_memory_used_bytes", "job": "integrations/redis"})
        is not None
    )


@pytest.mark.parametrize(
    "expression",
    [
        "sum by (handler) (http_requests_total)",
        'http_request_duration_seconds_bucket{method="GET"}',
        'http_requests_total{status="500"}',
        'node_cpu_seconds_total{mode="system"}',
        "sum(node_cpu_seconds_total)",
    ],
)
def test_removed_dimensions_fail_contract(expression: str) -> None:
    with pytest.raises(ValueError):
        validate_labels(Query("test-panel", expression, False))


@pytest.mark.parametrize("mutation", ["new-metric", "bypass", "late-drop"])
def test_contract_rejects_pipeline_drift(tmp_path: Path, mutation: str) -> None:
    shutil.copytree(ROOT / "observability/grafana", tmp_path / "observability/grafana")
    target = tmp_path / "observability/alloy/config.prod.alloy"
    target.parent.mkdir(parents=True)
    config = (ROOT / "observability/alloy/config.prod.alloy").read_text()
    if mutation == "new-metric":
        (tmp_path / "observability/grafana/dashboards/new.json").write_text(
            '{"panels":[{"targets":[{"expr":"new_metric_total"}]}]}'
        )
    elif mutation == "bypass":
        config = config.replace(
            "prometheus.relabel.production_metrics.receiver",
            "prometheus.remote_write.grafana_cloud.receiver",
            1,
        )
    else:
        config = config.replace(
            "// END METRIC ALLOWLIST",
            """// END METRIC ALLOWLIST
  rule {
    source_labels = ["__name__"]
    regex = "pg_up"
    action = "drop"
  }""",
        )
    target.write_text(config)
    with pytest.raises(ValueError):
        validate(tmp_path)
