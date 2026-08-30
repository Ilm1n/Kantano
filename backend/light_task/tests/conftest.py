from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest
import pytest_asyncio
import redis.asyncio as redis
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from alembic import command

if sys.platform.startswith("win") and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _setup_test_env() -> None:
    test_dir = Path(__file__).resolve().parent
    test_private_key = test_dir / "fixtures" / "jwt-private.pem"
    test_public_key = test_dir / "fixtures" / "jwt-public.pem"

    if not test_private_key.exists() or not test_public_key.exists():
        raise RuntimeError(
            "Missing test JWT keys in tests/fixtures. "
            "Expected jwt-private.pem and jwt-public.pem for CI/local integration runs."
        )

    os.environ.setdefault("LIGHTTASK_TESTING", "1")

    os.environ.setdefault(
        "LIGHTTASK_CONFIG__DB__HOST",
        os.getenv("LIGHTTASK_TEST_DB_HOST", "127.0.0.1"),
    )
    os.environ.setdefault(
        "LIGHTTASK_CONFIG__DB__PORT",
        os.getenv("LIGHTTASK_TEST_DB_PORT", "55432"),
    )
    os.environ.setdefault(
        "LIGHTTASK_CONFIG__DB__USER",
        os.getenv("LIGHTTASK_TEST_DB_USER", "postgres"),
    )
    os.environ.setdefault(
        "LIGHTTASK_CONFIG__DB__PASSWORD",
        os.getenv("LIGHTTASK_TEST_DB_PASSWORD", "postgres"),
    )
    os.environ.setdefault(
        "LIGHTTASK_CONFIG__DB__NAME",
        os.getenv("LIGHTTASK_TEST_DB_NAME", "lighttask_test"),
    )

    os.environ.setdefault("LIGHTTASK_CONFIG__S3__ACCESS_KEY", "test")
    os.environ.setdefault("LIGHTTASK_CONFIG__S3__SECRET_KEY", "test")
    os.environ.setdefault("LIGHTTASK_CONFIG__S3__BUCKET_NAME", "test")
    os.environ.setdefault("LIGHTTASK_CONFIG__AUTH_JWT__SECURE", "False")
    os.environ.setdefault("LIGHTTASK_CONFIG__FRONTEND__BASE_URL", "http://localhost:5173")
    os.environ.setdefault("LIGHTTASK_CONFIG__YANDEX__CLIENT_ID", "test-client-id")
    os.environ.setdefault("LIGHTTASK_CONFIG__YANDEX__CLIENT_SECRET", "test-client-secret")
    os.environ.setdefault(
        "LIGHTTASK_CONFIG__YANDEX__REDIRECT_URI",
        "http://testserver/api/auth/yandex/callback",
    )
    os.environ.setdefault(
        "LIGHTTASK_CONFIG__AUTH_JWT__PRIVATE_KEY_PATH",
        str(test_private_key),
    )
    os.environ.setdefault(
        "LIGHTTASK_CONFIG__AUTH_JWT__PUBLIC_KEY_PATH",
        str(test_public_key),
    )

    os.environ.setdefault(
        "LIGHTTASK_CONFIG__REALTIME__REDIS_URL",
        os.getenv("LIGHTTASK_TEST_REDIS_URL", "redis://127.0.0.1:56379/15"),
    )
    os.environ.setdefault("LIGHTTASK_CONFIG__REALTIME__PRESENCE_TTL_SECONDS", "2")
    os.environ.setdefault("LIGHTTASK_CONFIG__REALTIME__PRESENCE_SYNC_INTERVAL_SECONDS", "1")
    os.environ.setdefault(
        "LIGHTTASK_CONFIG__QUEUE__HOST",
        os.getenv("LIGHTTASK_TEST_RABBITMQ_HOST", "127.0.0.1"),
    )
    os.environ.setdefault(
        "LIGHTTASK_CONFIG__QUEUE__PORT",
        os.getenv("LIGHTTASK_TEST_RABBITMQ_PORT", "55672"),
    )
    os.environ.setdefault("LIGHTTASK_CONFIG__QUEUE__USER", "lighttask")
    os.environ.setdefault("LIGHTTASK_CONFIG__QUEUE__PASSWORD", "lighttask-test")
    os.environ.setdefault("LIGHTTASK_CONFIG__QUEUE__VIRTUAL_HOST", "kantano")

    _validate_test_isolation()


def _validate_test_isolation() -> None:
    if os.getenv("LIGHTTASK_TEST_ALLOW_NON_TEST_DB") == "1":
        return

    db_name = os.environ.get("LIGHTTASK_CONFIG__DB__NAME", "")
    if "test" not in db_name.lower():
        raise RuntimeError(
            "Refusing to run integration tests against non-test database. "
            "Set LIGHTTASK_TEST_DB_NAME to a dedicated test DB or explicitly set "
            "LIGHTTASK_TEST_ALLOW_NON_TEST_DB=1."
        )

    redis_url = os.environ.get("LIGHTTASK_CONFIG__REALTIME__REDIS_URL", "")
    parsed = urlparse(redis_url)
    redis_db = parsed.path.lstrip("/")
    if redis_db in {"", "0"}:
        raise RuntimeError(
            "Refusing to run integration tests against Redis DB 0. "
            "Use a dedicated Redis DB index (for example /15) via LIGHTTASK_TEST_REDIS_URL."
        )


_setup_test_env()

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import settings  # noqa: E402
from src.db.database import db_helper  # noqa: E402
from src.main import main_app  # noqa: E402


def _all_selected_tests_are_infra_free(config: pytest.Config) -> bool:
    items = getattr(config, "_lighttask_selected_items", [])
    return bool(items) and all(item.get_closest_marker("no_infra") for item in items)


def pytest_collection_modifyitems(
    session: pytest.Session,
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    config._lighttask_selected_items = items  # type: ignore[attr-defined]


@pytest.fixture(scope="session", autouse=True)
def apply_migrations(request: pytest.FixtureRequest) -> None:
    if _all_selected_tests_are_infra_free(request.config):
        return

    root = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(root / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")


@pytest_asyncio.fixture
async def redis_client() -> redis.Redis:
    client = redis.from_url(
        settings.realtime.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    await client.ping()
    yield client
    await client.aclose()


@pytest_asyncio.fixture(autouse=True)
async def clean_state(
    request: pytest.FixtureRequest,
) -> None:
    if request.node.get_closest_marker("no_infra"):
        yield
        return

    redis_client = redis.from_url(
        settings.realtime.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    await redis_client.ping()

    async with db_helper.async_session_maker() as session:
        result = await session.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename <> 'alembic_version'"
            )
        )
        table_names = [row[0] for row in result.fetchall()]
        if table_names:
            quoted = ", ".join(f'"{name}"' for name in table_names)
            await session.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
            await session.commit()

    await redis_client.flushdb()
    yield

    async with db_helper.async_session_maker() as session:
        result = await session.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename <> 'alembic_version'"
            )
        )
        table_names = [row[0] for row in result.fetchall()]
        if table_names:
            quoted = ", ".join(f'"{name}"' for name in table_names)
            await session.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
            await session.commit()
    await redis_client.flushdb()
    await redis_client.aclose()


@pytest.fixture
def client() -> TestClient:
    with TestClient(main_app) as test_client:
        yield test_client
