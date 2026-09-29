from __future__ import annotations

import importlib.util
from io import BytesIO
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, call
from urllib.error import HTTPError, URLError

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


def _successful_response() -> MagicMock:
    response = MagicMock()
    response.__enter__.return_value.status = 200
    response.__enter__.return_value.read.return_value = b'{"uid": "kantano"}'
    return response


@pytest.mark.parametrize("status", [502, 503, 504])
@pytest.mark.parametrize("failures", [1, 5])
def test_request_retries_transient_http_errors(
    monkeypatch: pytest.MonkeyPatch, status: int, failures: int
) -> None:
    module = _load_apply_module()
    errors = [
        HTTPError(
            "http://grafana/api/folders/kantano",
            status,
            "Unavailable",
            {},
            BytesIO(b'{"code": "Loading"}'),
        )
        for _ in range(failures)
    ]
    urlopen = MagicMock(side_effect=[*errors, _successful_response()])
    sleep = MagicMock()
    monkeypatch.setattr(module, "urlopen", urlopen)
    monkeypatch.setattr(module.time, "sleep", sleep)

    if failures == 5:
        with pytest.raises(RuntimeError, match=rf"failed \({status}\).*Loading"):
            module.request("GET", "/api/folders/kantano")
        assert urlopen.call_count == 5
        assert sleep.call_args_list == [call(15)] * 4
    else:
        assert module.request("GET", "/api/folders/kantano") == (200, {"uid": "kantano"})
        assert urlopen.call_count == 2
        sleep.assert_called_once_with(15)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 500])
def test_request_does_not_retry_other_http_errors(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    module = _load_apply_module()
    error = HTTPError("http://grafana", status, "Error", {}, BytesIO(b"error"))
    urlopen = MagicMock(side_effect=error)
    sleep = MagicMock()
    monkeypatch.setattr(module, "urlopen", urlopen)
    monkeypatch.setattr(module.time, "sleep", sleep)

    if status == 404:
        assert module.request("GET", "/api/folders/kantano") == (404, None)
    else:
        with pytest.raises(RuntimeError, match=rf"failed \({status}\)"):
            module.request("GET", "/api/folders/kantano")
    assert urlopen.call_count == 1
    sleep.assert_not_called()


@pytest.mark.parametrize(
    "error", [URLError("connection failed"), TimeoutError("timed out"), ConnectionResetError()]
)
@pytest.mark.parametrize("failures", [1, 5])
def test_request_retries_network_errors(
    monkeypatch: pytest.MonkeyPatch, error: Exception, failures: int
) -> None:
    module = _load_apply_module()
    urlopen = MagicMock(side_effect=[error] * failures + [_successful_response()])
    sleep = MagicMock()
    monkeypatch.setattr(module, "urlopen", urlopen)
    monkeypatch.setattr(module.time, "sleep", sleep)

    if failures == 5:
        with pytest.raises(type(error)):
            module.request("GET", "/api/folders/kantano")
        assert urlopen.call_count == 5
        assert sleep.call_args_list == [call(15)] * 4
    else:
        assert module.request("GET", "/api/folders/kantano") == (200, {"uid": "kantano"})
        assert urlopen.call_count == 2
        sleep.assert_called_once_with(15)
