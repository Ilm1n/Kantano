from __future__ import annotations

import asyncio
import ssl
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from src.assistant import provider
from src.assistant.tool_schemas import TOOL_SCHEMAS, SelectTaskReferences, validate_write
from src.config import AssistantConfig, Settings, settings

pytestmark = pytest.mark.no_infra


def test_gigachat_selection_excludes_other_cloud_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = AssistantConfig(
        enabled=True,
        mode="cloud",
        cloud_provider="ru",
        gigachat_credentials="test-key",
        google_api_key="unused-google",
        groq_api_key="unused-groq",
    )
    monkeypatch.setattr(settings, "assistant", config)
    models = provider.available_models()
    assert [(name, model) for name, model, _ in models] == [("gigachat", "GigaChat-2")]
    model = models[0][2]
    assert model is provider.available_models()[0][2]
    assert model.verify_ssl_certs is True
    assert model.max_retries == 0
    assert model.ssl_context.verify_mode == ssl.CERT_REQUIRED
    assert model.ssl_context.check_hostname
    assert len(model.ssl_context.get_ca_certs()) > 1
    # Bind all existing schemas, including nested plans, through the real SDK.
    schemas = model.bind_tools(provider.gigachat_tools(TOOL_SCHEMAS)).kwargs["tools"]
    assert len(schemas) == len(TOOL_SCHEMAS)
    plan = next(
        schema["function"] for schema in schemas if schema["function"]["name"] == "ExecutePlan"
    )
    assert (
        plan["parameters"]["properties"]["steps"]["items"]["properties"]["args"]["type"] == "string"
    )
    assert model.bind_tools([SelectTaskReferences], tool_choice="SelectTaskReferences").kwargs[
        "function_call"
    ] == {"name": "SelectTaskReferences"}


def test_local_mode_never_uses_gigachat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings,
        "assistant",
        AssistantConfig(mode="local", cloud_provider="ru", gigachat_credentials="unused"),
    )
    assert [name for name, _, _ in provider.available_models()] == ["lmstudio"]


def test_global_chain_keeps_google_and_groq(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings,
        "assistant",
        AssistantConfig(google_api_key="google-key", groq_api_key="groq-key"),
    )
    assert [name for name, _, _ in provider.available_models()] == ["google", "google", "groq"]


def test_gigachat_requires_existing_ca_file(tmp_path: Path) -> None:
    data = settings.model_dump()
    data["assistant"] = AssistantConfig(
        enabled=True,
        cloud_provider="ru",
        gigachat_credentials="test-key",
        gigachat_ca_bundle_file=tmp_path / "missing.pem",
    ).model_dump()
    with pytest.raises(ValidationError, match="GigaChat CA bundle file does not exist"):
        Settings.model_validate(data)


def test_plan_transport_preserves_arguments_and_validation() -> None:
    args = {
        "steps": [
            {"id": "column", "tool": "CreateColumn", "args": {"name": "Column"}},
            {
                "id": "task",
                "tool": "CreateTask",
                "args": {"title": "Task", "column_id": "$column.column_id"},
            },
        ]
    }
    message = AIMessage(
        content="", tool_calls=[{"name": "ExecutePlan", "args": args, "id": "call"}]
    )
    encoded = provider.gigachat_plan_arguments(message, encode=True)
    assert isinstance(encoded, AIMessage)
    assert isinstance(encoded.tool_calls[0]["args"]["steps"][0]["args"], str)
    assert message.tool_calls[0]["args"] == args
    decoded = provider.gigachat_plan_arguments(encoded, encode=False)
    assert isinstance(decoded, AIMessage)
    assert validate_write("ExecutePlan", decoded.tool_calls[0]["args"]) == args


@pytest.mark.parametrize("credentials", ["", "test-key"])
def test_gigachat_settings_require_its_own_credentials(credentials: str) -> None:
    data = settings.model_dump()
    data["assistant"] = AssistantConfig(
        enabled=True,
        cloud_provider="ru",
        gigachat_credentials=credentials,
        google_api_key="does-not-satisfy-gigachat",
    ).model_dump()
    if credentials:
        assert Settings.model_validate(data).assistant.cloud_provider == "ru"
    else:
        with pytest.raises(ValidationError, match="GigaChat credentials are required"):
            Settings.model_validate(data)


class FakeGigaChat:
    def __init__(self) -> None:
        self.choices: list[str | None] = []
        self.active = 0
        self.maximum_active = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    def bind_tools(self, tools: list[type], *, tool_choice: str | None = None) -> FakeGigaChat:
        self.choices.append(tool_choice)
        return self

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        self.entered.set()
        try:
            await self.release.wait()
            return AIMessage(
                content="ok",
                usage_metadata={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
            )
        finally:
            self.active -= 1


def test_forced_selection_uses_named_tool_and_preserves_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = FakeGigaChat()
    model.release.set()
    monkeypatch.setattr(provider, "available_models", lambda: [("gigachat", "model", model)])
    result = asyncio.run(provider.call_model([], [SelectTaskReferences], tool_choice="required"))
    assert model.choices == ["SelectTaskReferences"]
    assert result.usage == provider.TokenUsage(10, 2)


def test_parallel_gigachat_calls_are_serialized(monkeypatch: pytest.MonkeyPatch) -> None:
    async def exercise() -> None:
        model = FakeGigaChat()
        monkeypatch.setattr(provider, "_gigachat_lock", asyncio.Lock())
        monkeypatch.setattr(provider, "available_models", lambda: [("gigachat", "model", model)])
        first = asyncio.create_task(provider.call_model([], []))
        await model.entered.wait()
        second = asyncio.create_task(provider.call_model([], []))
        await asyncio.sleep(0)
        assert model.active == 1 and not second.done()
        model.release.set()
        await asyncio.gather(first, second)
        assert model.maximum_active == 1

    asyncio.run(exercise())


@pytest.mark.parametrize("cancel_waiting", [False, True])
def test_cancel_releases_gigachat_slot(
    monkeypatch: pytest.MonkeyPatch, cancel_waiting: bool
) -> None:
    async def exercise() -> None:
        model = FakeGigaChat()
        monkeypatch.setattr(provider, "_gigachat_lock", asyncio.Lock())
        monkeypatch.setattr(provider, "available_models", lambda: [("gigachat", "model", model)])
        first = asyncio.create_task(provider.call_model([], []))
        await model.entered.wait()
        second = asyncio.create_task(provider.call_model([], []))
        await asyncio.sleep(0)
        cancelled, remaining = (second, first) if cancel_waiting else (first, second)
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        model.release.set()
        await remaining
        assert model.active == 0
        assert not provider._gigachat_lock.locked()

    asyncio.run(exercise())
