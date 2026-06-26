from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.no_infra

SRC_DIR = Path(__file__).resolve().parents[1] / "src"


def _python_files() -> list[Path]:
    return list(SRC_DIR.rglob("*.py"))


def test_legacy_service_files_are_removed() -> None:
    service_files = sorted(path.relative_to(SRC_DIR) for path in SRC_DIR.rglob("service.py"))

    assert service_files == []


def test_routers_do_not_depend_on_legacy_services() -> None:
    offenders = []
    for path in _python_files():
        if path.name != "router.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "Depends(get_" in text and "_service" in text:
            offenders.append(path.relative_to(SRC_DIR))

    assert offenders == []


def test_commit_and_rollback_are_owned_by_unit_of_work() -> None:
    allowed = SRC_DIR / "db" / "unit_of_work.py"
    offenders = []
    for path in _python_files():
        if path == allowed:
            continue
        text = path.read_text(encoding="utf-8")
        if "session.commit(" in text or "session.rollback(" in text:
            offenders.append(path.relative_to(SRC_DIR))

    assert offenders == []


def test_realtime_publish_stays_in_dispatchers_or_realtime_infrastructure() -> None:
    offenders = []
    for path in _python_files():
        text = path.read_text(encoding="utf-8")
        if "publish_event(" not in text:
            continue

        relative = path.relative_to(SRC_DIR)
        if "realtimev1" in relative.parts or path.name == "events.py":
            continue
        offenders.append(relative)

    assert offenders == []
