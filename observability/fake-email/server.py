from __future__ import annotations

import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from typing import Any, ClassVar

HOST = "0.0.0.0"  # noqa: S104 - isolated Compose verification network
PORT = 8080
MAX_BODY_BYTES = 128 * 1024

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("fake-email")


class ProviderState:
    _VALID_MODES: ClassVar[set[str]] = {
        "success",
        "transient_once",
        "fail_always",
    }

    def __init__(self) -> None:
        self._lock = Lock()
        self._mode = "success"
        self._attempts = 0
        self._accepted = 0
        self._idempotency_keys: list[str] = []

    def reset(self, mode: str) -> dict[str, Any]:
        if mode not in self._VALID_MODES:
            raise ValueError(f"Unsupported mode: {mode}")
        with self._lock:
            self._mode = mode
            self._attempts = 0
            self._accepted = 0
            self._idempotency_keys = []
            return self._snapshot_unlocked()

    def record_attempt(self, idempotency_key: str) -> tuple[int, dict[str, Any]]:
        with self._lock:
            self._attempts += 1
            self._idempotency_keys.append(idempotency_key)
            should_fail = self._mode == "fail_always" or (
                self._mode == "transient_once" and self._attempts == 1
            )
            if should_fail:
                status = HTTPStatus.SERVICE_UNAVAILABLE
            else:
                self._accepted += 1
                status = HTTPStatus.OK
            return int(status), self._snapshot_unlocked()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_unlocked()

    def _snapshot_unlocked(self) -> dict[str, Any]:
        return {
            "mode": self._mode,
            "attempts": self._attempts,
            "accepted": self._accepted,
            "idempotency_keys": list(self._idempotency_keys),
        }


STATE = ProviderState()


class Handler(BaseHTTPRequestHandler):
    server_version = "KantanoFakeEmail/1.0"
    state: ClassVar[ProviderState] = STATE

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(HTTPStatus.OK, {"status": "ok"})
            return
        if self.path == "/__state":
            self._json(HTTPStatus.OK, self.state.snapshot())
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path == "/__control":
            payload = self._read_json()
            try:
                snapshot = self.state.reset(str(payload.get("mode", "success")))
            except ValueError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._json(HTTPStatus.OK, snapshot)
            return

        if self.path == "/emails":
            self._read_json()
            idempotency_key = self.headers.get("Idempotency-Key", "")
            status, snapshot = self.state.record_attempt(idempotency_key)
            logger.info(
                "email attempt result=%s attempt=%s",
                "accepted" if status == HTTPStatus.OK else "transient_failure",
                snapshot["attempts"],
            )
            self._json(status, {"id": f"fake-{snapshot['attempts']}"})
            return

        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length < 0 or length > MAX_BODY_BYTES:
            self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return {}
        body = self.rfile.read(length)
        if not body:
            return {}
        try:
            decoded = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return decoded if isinstance(decoded, dict) else {}

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    logger.info("fake email provider started port=%s", PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        logger.info("fake email provider stopped")


if __name__ == "__main__":
    main()
