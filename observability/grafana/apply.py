from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
BASE_URL = os.environ.get("GRAFANA_URL", "http://grafana:3000").rstrip("/")
FOLDER_UID = "kantano"


def _authorization() -> str:
    token = os.environ.get("GRAFANA_TOKEN", "")
    if token:
        return f"Bearer {token}"
    user = os.environ.get("GRAFANA_USER", "admin")
    password = os.environ.get("GRAFANA_PASSWORD", "admin")
    encoded = base64.b64encode(f"{user}:{password}".encode()).decode()
    return f"Basic {encoded}"


def request(method: str, path: str, payload: Any | None = None) -> tuple[int, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(
        f"{BASE_URL}{path}",
        data=data,
        method=method,
        headers={"Authorization": _authorization(), "Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=20) as response:  # noqa: S310 - operator-supplied URL.
            body = response.read()
            return response.status, json.loads(body) if body else None
    except HTTPError as exc:
        body = exc.read().decode(errors="replace")
        if exc.code == 404:
            return 404, None
        raise RuntimeError(
            f"Grafana API {method} {path} failed ({exc.code}): {body}"
        ) from exc


def ensure_folder() -> None:
    status, _ = request("GET", f"/api/folders/{FOLDER_UID}")
    if status == 404:
        request("POST", "/api/folders", {"uid": FOLDER_UID, "title": "Kantano"})


def _replace_datasource_uids(value: Any) -> Any:
    replacements = {
        "kantano-prometheus": os.environ.get(
            "GRAFANA_PROMETHEUS_UID", "kantano-prometheus"
        ),
        "kantano-loki": os.environ.get("GRAFANA_LOKI_UID", "kantano-loki"),
        "kantano-tempo": os.environ.get("GRAFANA_TEMPO_UID", "kantano-tempo"),
        "kantano-usage": os.environ.get("GRAFANA_USAGE_UID", "kantano-prometheus"),
    }
    if isinstance(value, dict):
        return {key: _replace_datasource_uids(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_datasource_uids(item) for item in value]
    if isinstance(value, str):
        return replacements.get(value, value)
    return value


def apply_dashboards() -> None:
    for path in sorted((ROOT / "dashboards").glob("*.json")):
        dashboard = _replace_datasource_uids(
            json.loads(path.read_text(encoding="utf-8"))
        )
        status, existing = request("GET", f"/api/dashboards/uid/{dashboard['uid']}")
        # Local Grafana loads dashboards from the read-only provisioning mount.
        # Grafana rejects API updates for those dashboards, while Grafana Cloud
        # dashboards are API-managed and should be updated idempotently.
        if status != 404 and existing.get("meta", {}).get("provisioned"):
            continue
        request(
            "POST",
            "/api/dashboards/db",
            {"dashboard": dashboard, "folderUid": FOLDER_UID, "overwrite": True},
        )


def _alert_payload(rule: dict[str, str]) -> dict[str, Any]:
    prometheus_uid = os.environ.get("GRAFANA_PROMETHEUS_UID", "kantano-prometheus")
    datasource_uid = (
        os.environ.get("GRAFANA_USAGE_UID", prometheus_uid)
        if rule.get("datasource") == "usage"
        else prometheus_uid
    )
    return {
        "uid": rule["uid"],
        "title": rule["title"],
        "ruleGroup": "Kantano",
        "folderUID": FOLDER_UID,
        "condition": "C",
        "data": [
            {
                "refId": "A",
                "queryType": "",
                "relativeTimeRange": {"from": 600, "to": 0},
                "datasourceUid": datasource_uid,
                "model": {
                    "datasource": {"type": "prometheus", "uid": datasource_uid},
                    "editorMode": "code",
                    "expr": rule["expr"],
                    "instant": True,
                    "refId": "A",
                },
            },
            {
                "refId": "C",
                "queryType": "",
                "relativeTimeRange": {"from": 0, "to": 0},
                "datasourceUid": "__expr__",
                "model": {
                    "conditions": [
                        {
                            "evaluator": {"params": [0], "type": "gt"},
                            "operator": {"type": "and"},
                            "query": {"params": ["C"]},
                            "reducer": {"params": [], "type": "last"},
                            "type": "query",
                        }
                    ],
                    "datasource": {"type": "__expr__", "uid": "__expr__"},
                    "expression": "A",
                    "refId": "C",
                    "type": "threshold",
                },
            },
        ],
        "noDataState": rule["noDataState"],
        "execErrState": "Error",
        "for": rule["for"],
        "annotations": {"summary": rule["summary"]},
        "labels": {"service": "kantano", "severity": "warning"},
        "isPaused": os.environ.get("PAUSE_ALERTS") == "1",
    }


def apply_alerts() -> None:
    rules = json.loads((ROOT / "alert-rules.json").read_text(encoding="utf-8"))
    for rule in rules:
        payload = _alert_payload(rule)
        status, _ = request("GET", f"/api/v1/provisioning/alert-rules/{rule['uid']}")
        if status == 404:
            request("POST", "/api/v1/provisioning/alert-rules", payload)
        else:
            request("PUT", f"/api/v1/provisioning/alert-rules/{rule['uid']}", payload)


def apply_telegram() -> None:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        if os.environ.get("REQUIRE_TELEGRAM") == "1":
            raise RuntimeError(
                "Telegram credentials are required for Grafana alert provisioning"
            )
        return
    contact = {
        "uid": "kantano-telegram",
        "name": "Kantano Telegram",
        "type": "telegram",
        "settings": {
            "bottoken": bot_token,
            "chatid": chat_id,
            "disable_web_page_preview": True,
        },
        "disableResolveMessage": False,
    }
    _, contact_points = request("GET", "/api/v1/provisioning/contact-points")
    existing = next(
        (item for item in contact_points if item.get("uid") == contact["uid"]),
        None,
    )
    if existing is None:
        request("POST", "/api/v1/provisioning/contact-points", contact)
    else:
        request(
            "PUT",
            f"/api/v1/provisioning/contact-points/{existing['uid']}",
            contact,
        )
    request(
        "PUT",
        "/api/v1/provisioning/policies",
        {
            "receiver": "Kantano Telegram",
            "group_by": ["service", "alertname"],
            "group_wait": "30s",
            "group_interval": "5m",
            "repeat_interval": "4h",
        },
    )


def main() -> None:
    ensure_folder()
    apply_dashboards()
    apply_alerts()
    apply_telegram()
    print("Grafana dashboards, alerts, and notification policy are up to date.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
