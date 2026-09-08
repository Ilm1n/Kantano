"""Offline dashboard/alert contract; never runs in the production ingest path."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import promql_parser as promql

ROOT = Path(__file__).resolve().parents[3]
EXTERNAL = frozenset(
    {
        "grafanacloud_instance_active_series",
        "grafanacloud_org_logs_usage",
        "grafanacloud_org_traces_usage",
    }
)
NAME = r"[a-zA-Z_:][a-zA-Z0-9_:]*"


@dataclass(frozen=True)
class Query:
    location: str
    expression: str
    external: bool


def queries(root: Path = ROOT) -> Iterator[Query]:
    def walk(value: Any, location: str, datasource: Any = None) -> Iterator[Query]:
        if isinstance(value, list):
            for index, child in enumerate(value):
                yield from walk(child, f"{location}[{index}]", datasource)
        elif isinstance(value, dict):
            datasource = value.get("datasource", datasource)
            for key, child in value.items():
                if key in {"expr", "query"} and isinstance(child, str):
                    if isinstance(datasource, dict):
                        kind, uid = datasource.get("type"), datasource.get("uid")
                    else:
                        kind, uid = "prometheus", datasource
                    if kind in {"loki", "tempo"}:
                        continue
                    if kind != "prometheus" or uid not in {
                        None,
                        "usage",
                        "kantano-usage",
                        "kantano-prometheus",
                    }:
                        raise ValueError(f"{location}: unknown query datasource {datasource!r}")
                    expression = child
                    if key == "query":
                        match = re.fullmatch(r"label_values\((.+),\s*([\w]+)\)", child)
                        if not match:
                            raise ValueError(f"{location}: unsupported Grafana variable {child!r}")
                        expression = match[1]
                    yield Query(location, expression, uid in {"usage", "kantano-usage"})
                elif isinstance(child, (dict, list)):
                    yield from walk(child, f"{location}.{key}", datasource)

    paths = sorted((root / "observability/grafana/dashboards").glob("*.json"))
    paths.append(root / "observability/grafana/alert-rules.json")
    for path in paths:
        yield from walk(json.loads(path.read_text(encoding="utf-8")), str(path.relative_to(root)))


def parse(expression: str) -> promql.Expr:
    # Only known duration macros are substituted; label-value variables remain strings.
    expression = expression.replace("$__range", "1h").replace("$__rate_interval", "5m")
    return promql.parse(expression)


def metrics(expression: str) -> set[str]:
    names: set[str] = set()

    def visit(node: promql.Expr) -> None:
        if not isinstance(node, promql.VectorSelector):
            return
        if node.matchers.or_matchers:
            raise ValueError("OR matchers are unsupported; use separate explicit selectors")
        if node.name:
            names.add(node.name)
        else:
            matchers = [m for m in node.matchers.matchers if m.name == "__name__"]
            if len(matchers) != 1:
                raise ValueError("Selector must specify a metric name or finite __name__ matcher")
            matcher = matchers[0]
            if matcher.op not in (promql.MatchOp.Equal, promql.MatchOp.Re):
                raise ValueError("Negative metric-name matchers cannot define an allowlist")
            pattern = NAME if matcher.op == promql.MatchOp.Equal else rf"{NAME}(\|{NAME})*"
            if not re.fullmatch(pattern, matcher.value):
                raise ValueError("__name__ regex must enumerate literal names separated by |")
            names.update(matcher.value.split("|"))

    promql.walk(parse(expression), visit)
    return names


def inventory(root: Path = ROOT) -> tuple[set[str], list[Query]]:
    local: set[str] = set()
    items = list(queries(root))
    if not items:
        raise ValueError("No queries discovered")
    for query in items:
        try:
            names = metrics(query.expression)
            if query.external:
                if names - EXTERNAL:
                    raise ValueError(f"Unknown external metrics: {sorted(names - EXTERNAL)}")
            elif names & EXTERNAL or any(n.startswith("grafanacloud_") for n in names):
                raise ValueError("Cloud usage metrics require the external usage datasource")
            else:
                local.update(names)
        except ValueError as exc:
            raise ValueError(f"{query.location}: {query.expression}\n{exc}") from exc
    return local, items


def allowlist(config: str) -> set[str]:
    blocks = re.findall(r"// BEGIN METRIC ALLOWLIST(.*?)// END METRIC ALLOWLIST", config, re.S)
    if len(blocks) != 1:
        raise ValueError("Expected exactly one marked production allowlist")
    block = blocks[0]
    if not re.search(r'action\s*=\s*"keep"', block):
        raise ValueError("Allowlist must use keep")
    if not re.search(r'source_labels\s*=\s*\["__name__"\]', block):
        raise ValueError("Allowlist must match __name__")
    patterns = re.findall(r'regex\s*=\s*"([^"\n]+)"', block)
    if len(patterns) != 1 or not re.fullmatch(rf"{NAME}(\|{NAME})*", patterns[0]):
        raise ValueError("Allowlist must enumerate exact metric names")
    return set(patterns[0].split("|"))


def production_filter(labels: dict[str, str], config: str | None = None) -> dict[str, str] | None:
    """Evaluate our deliberately small relabel subset for contract/scrape verification.

    Unknown actions fail rather than pretending a new production rule is compatible.
    Alloy itself remains the runtime executor and syntax authority.
    """
    if config is None:
        config = (ROOT / "observability/alloy/config.prod.alloy").read_text()
    component = config.split('prometheus.relabel "production_metrics" {')[1].split(
        'prometheus.remote_write "grafana_cloud"'
    )[0]
    result = dict(labels)
    for block in re.findall(r"rule\s*\{([^{}]*)\}", component):

        def field(name: str, default: str = "", block: str = block) -> str:
            match = re.search(rf'{name}\s*=\s*"([^"]*)"', block)
            return match[1] if match else default

        source = re.search(r"source_labels\s*=\s*\[([^]]*)\]", block)
        keys = re.findall(r'"([^"]+)"', source[1]) if source else []
        value = field("separator", ";").join(result.get(key, "") for key in keys)
        matched = re.fullmatch(field("regex", "(.*)"), value)
        action = field("action", "replace")
        if (action == "keep" and not matched) or (action == "drop" and matched):
            return None
        if action == "replace" and matched:
            replacement = re.sub(r"\$(\d+)", r"\\g<\1>", field("replacement", "$1"))
            result[field("target_label")] = matched.expand(replacement)
        elif action == "labeldrop":
            result = {k: v for k, v in result.items() if not re.fullmatch(field("regex"), k)}
        elif action not in {"keep", "drop", "replace"}:
            raise ValueError(f"Unsupported relabel action: {action}")
    return result


def representative_labels(name: str) -> dict[str, str]:
    job = "alloy"
    for prefix, producer in (
        ("http_", "kantano-api"),
        ("kantano_cache_", "kantano-api"),
        ("kantano_db_", "kantano-api"),
        ("kantano_realtime_", "kantano-api"),
        ("kantano_outbox_", "kantano-outbox-publisher"),
        ("kantano_celery_", "kantano-celery-worker"),
        ("node_", "integrations/unix"),
        ("container_", "integrations/cadvisor"),
        ("pg_", "integrations/postgres"),
        ("redis_", "integrations/redis"),
        ("rabbitmq_", "rabbitmq"),
    ):
        if name.startswith(prefix):
            job = producer
            break
    return {
        "__name__": name,
        "job": job,
        "environment": "production",
        "instance": "test",
        "mode": "idle",
        "mountpoint": "/",
        "fstype": "ext4",
        "status": "5xx",
        "container_label_com_docker_compose_project": "lighttask_prod",
        "container_label_com_docker_compose_service": "backend",
    }


def validate(root: Path = ROOT) -> list[Query]:
    required, items = inventory(root)
    config = (root / "observability/alloy/config.prod.alloy").read_text(encoding="utf-8")
    allowed = allowlist(config)
    if required != allowed:
        missing = required - allowed
        locations = [q.location for q in items if metrics(q.expression) & missing]
        raise ValueError(
            f"Missing metrics: {sorted(missing)}; used at {locations}; "
            f"unused allowlist metrics: {sorted(allowed - required)}"
        )
    for query in items:
        validate_labels(query)
    for name in required:
        if production_filter(representative_labels(name), config) is None:
            raise ValueError(f"Required metric is dropped by production relabel rules: {name}")
    # Fail closed on topology changes. Only this one component may forward to remote_write.
    components = re.split(r'(?m)^(?=[a-z][\w.]*\s+"[^"]+"\s*\{)', config)
    remote_edges = []
    for component in components:
        heading = component.partition("{")[0].strip()
        if "prometheus.remote_write.grafana_cloud.receiver" in component:
            remote_edges.append(heading)
        if heading.startswith("prometheus.scrape"):
            expected = "prometheus.relabel.production_metrics.receiver"
            if not re.search(r"forward_to\s*=\s*\[" + re.escape(expected) + r"\]", component):
                raise ValueError(f"Scrape bypasses production contract: {heading}")
    if remote_edges != ['prometheus.relabel "production_metrics"']:
        raise ValueError(f"Unexpected remote_write edges: {remote_edges}")
    return items


def validate_labels(query: Query) -> None:
    """Reject known-incompatible selectors/groupings even if metric names still match."""
    used: set[str] = set()
    selectors: list[promql.VectorSelector] = []

    def visit(node: promql.Expr) -> None:
        if isinstance(node, promql.VectorSelector):
            selectors.append(node)
            used.update(m.name for m in node.matchers.matchers)
        if isinstance(node, promql.AggregateExpr) and node.modifier:
            used.update(node.modifier.labels)
        if isinstance(node, promql.BinaryExpr) and node.modifier:
            if node.modifier.matching:
                used.update(node.modifier.matching.labels)
            used.update(node.modifier.group_labels or [])

    promql.walk(parse(query.expression), visit)
    for selector in selectors:
        forbidden = set()
        if selector.name == "http_requests_total":
            forbidden = {"handler", "method"}
        elif selector.name == "http_request_duration_seconds_bucket":
            forbidden = {"method", "status"}
        if used & forbidden:
            raise ValueError(f"{query.location}: removed HTTP labels {sorted(used & forbidden)}")
        for matcher in selector.matchers.matchers:
            if selector.name == "http_requests_total" and matcher.name == "status":
                if matcher.op == promql.MatchOp.Equal and not re.fullmatch(
                    "[1-5]xx", matcher.value
                ):
                    raise ValueError(f"{query.location}: status must select a grouped HTTP class")
            if selector.name == "node_cpu_seconds_total" and matcher.name == "mode":
                if matcher.op != promql.MatchOp.Equal or matcher.value != "idle":
                    raise ValueError(f"{query.location}: production CPU supports only idle mode")
        if selector.name == "node_cpu_seconds_total" and not any(
            m.name == "mode" for m in selector.matchers.matchers
        ):
            raise ValueError(f"{query.location}: CPU queries must explicitly select idle mode")


def check_promtool(items: list[Query]) -> None:
    rules = [
        {"record": f"contract_{index}", "expr": str(parse(q.expression))}
        for index, q in enumerate(items)
    ]
    with tempfile.TemporaryDirectory(prefix="kantano-promql-") as directory:
        path = Path(directory) / "rules.json"
        path.write_text(json.dumps({"groups": [{"name": "contract", "rules": rules}]}))
        docker = shutil.which("docker")
        if docker is None:
            raise ValueError("Docker is required for --promtool")
        subprocess.run(  # noqa: S603 - fixed executable and read-only temporary rules.
            [
                docker,
                "run",
                "--rm",
                "--entrypoint",
                "promtool",
                "-v",
                f"{path}:/rules.json:ro",
                "prom/prometheus:v3.5.1",
                "check",
                "rules",
                "/rules.json",
            ],
            check=True,
        )
        # Exercise real dashboard queries against grouped counters and bucket-only data.
        dashboard = json.loads((ROOT / "observability/grafana/dashboards/api.json").read_text())
        expected = {
            "Requests / second": [1.0],
            "5xx error ratio": [0.1],
            "Latency by route (p95)": [0.0975],
            "Cache hit ratio": [0.75],
        }
        cases = []
        for panel in dashboard["panels"]:
            for index, target in enumerate(panel.get("targets", [])):
                values = expected.get(panel["title"])
                if target.get("legendFormat") in {"p50", "p95", "p99"}:
                    value = {"p50": 0.075, "p95": 0.0975, "p99": 0.0995}[target["legendFormat"]]
                elif values:
                    value = values[index]
                else:
                    continue
                expression = (
                    target["expr"]
                    .replace("$environment", "production")
                    .replace("$job", "kantano-api")
                )
                if panel["title"] == "Latency by route (p95)":
                    labels = '{handler="/items/{id}"}'
                elif panel["title"] == "Cache hit ratio":
                    labels = '{cache="project_board"}'
                else:
                    labels = "{}"
                cases.append(
                    {
                        "expr": expression,
                        "eval_time": "10m",
                        "exp_samples": [{"labels": labels, "value": value}],
                    }
                )
        base = 'environment="production",job="kantano-api"'
        inputs = [
            {"series": f'http_requests_total{{{base},status="{status}"}}', "values": f"0+{step}x10"}
            for status, step in (("2xx", 48), ("4xx", 6), ("5xx", 6))
        ]
        inputs.extend(
            {
                "series": (
                    "kantano_cache_operations_total{"
                    f'{base},cache="project_board",operation="get",result="{result}"'
                    "}"
                ),
                "values": f"0+{step}x10",
            }
            for result, step in (("hit", 45), ("miss", 15))
        )
        for boundary in (
            "0.005",
            "0.01",
            "0.025",
            "0.05",
            "0.1",
            "0.25",
            "0.5",
            "1",
            "2.5",
            "5",
            "10",
            "+Inf",
        ):
            inputs.append(
                {
                    "series": f'http_request_duration_seconds_bucket{{{base},handler="/items/{{id}}",le="{boundary}"}}',
                    "values": f"0+{60 if float(boundary) >= 0.1 else 0}x10",
                }
            )
        path.write_text(
            json.dumps(
                {
                    "rule_files": [],
                    "fuzzy_compare": True,
                    "tests": [
                        {
                            "interval": "1m",
                            "input_series": inputs,
                            "promql_expr_test": cases,
                        }
                    ],
                }
            )
        )
        subprocess.run(  # noqa: S603 - fixed executable and read-only test fixture.
            [
                docker,
                "run",
                "--rm",
                "--entrypoint",
                "promtool",
                "-v",
                f"{path}:/rules.json:ro",
                "prom/prometheus:v3.5.1",
                "test",
                "rules",
                "/rules.json",
            ],
            check=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--promtool", action="store_true")
    args = parser.parse_args()
    if args.inventory:
        names, _ = inventory()
        print("\n".join(sorted(names)))
        return
    items = validate()
    if args.promtool:
        check_promtool(items)
    print(f"Observability contract OK: {len(items)} queries; {len(inventory()[0])} local metrics")


if __name__ == "__main__":
    main()
