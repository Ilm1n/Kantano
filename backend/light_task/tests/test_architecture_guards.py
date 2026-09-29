from __future__ import annotations

import ast
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


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)] + [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]


def test_routers_and_assistant_adapters_do_not_import_persistence() -> None:
    paths = [path for path in _python_files() if path.name == "router.py"]
    paths += [SRC_DIR / "assistant" / name for name in ("tools.py", "runtime.py", "graph.py")]
    offenders = [
        path.relative_to(SRC_DIR)
        for path in paths
        if any(
            module.startswith("sqlalchemy") or module.endswith((".models", ".repository"))
            for module in _imports(path)
        )
    ]
    assert offenders == []


def test_application_layer_does_not_build_sql_or_depend_on_http() -> None:
    paths = [*SRC_DIR.rglob("use_cases.py"), SRC_DIR / "assistant" / "queries.py"]
    offenders = [
        path.relative_to(SRC_DIR)
        for path in paths
        if any(
            module in {"sqlalchemy", "fastapi", "starlette.responses"} for module in _imports(path)
        )
    ]
    assert offenders == []


def test_projects_application_does_not_depend_on_assistant_or_langgraph() -> None:
    imports = _imports(SRC_DIR / "projects" / "use_cases.py")
    assert not any(module.startswith(("src.assistant", "langgraph")) for module in imports)


def test_rest_routers_do_not_open_database_transactions_or_sessions() -> None:
    offenders = []
    for path in SRC_DIR.rglob("router.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for endpoint in tree.body:
            if not isinstance(endpoint, ast.AsyncFunctionDef):
                continue
            if not any(
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr in {"get", "post", "put", "patch", "delete"}
                for decorator in endpoint.decorator_list
            ):
                continue
            for node in ast.walk(endpoint):
                if not isinstance(node, ast.AsyncWith):
                    continue
                for item in node.items:
                    call = item.context_expr
                    if not isinstance(call, ast.Call):
                        continue
                    function = call.func
                    if (isinstance(function, ast.Name) and function.id == "UnitOfWork") or (
                        isinstance(function, ast.Attribute)
                        and function.attr == "async_session_maker"
                    ):
                        offenders.append(path.relative_to(SRC_DIR))
    assert offenders == []
