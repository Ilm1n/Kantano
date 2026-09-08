from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.no_infra


def _load_apply_module() -> ModuleType:
    path = Path(__file__).parents[3] / "observability" / "grafana" / "apply.py"
    spec = importlib.util.spec_from_file_location("grafana_apply", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("existing", [False, True])
def test_apply_telegram_is_idempotent(monkeypatch: pytest.MonkeyPatch, existing: bool) -> None:
    module = _load_apply_module()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    calls: list[tuple[str, str, Any | None]] = []

    def request(method: str, path: str, payload: Any | None = None) -> tuple[int, Any]:
        calls.append((method, path, payload))
        if method == "GET":
            contact_points = (
                [{"uid": "kantano-telegram", "name": "Kantano Telegram"}] if existing else []
            )
            return 200, contact_points
        return 202, None

    monkeypatch.setattr(module, "request", request)

    module.apply_telegram()

    write_method = "PUT" if existing else "POST"
    write_path = (
        "/api/v1/provisioning/contact-points/kantano-telegram"
        if existing
        else "/api/v1/provisioning/contact-points"
    )
    assert calls[0] == ("GET", "/api/v1/provisioning/contact-points", None)
    assert calls[1][0:2] == (write_method, write_path)
    assert calls[2][0:2] == ("PUT", "/api/v1/provisioning/policies")
