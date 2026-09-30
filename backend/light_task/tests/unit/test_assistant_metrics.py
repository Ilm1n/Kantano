from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from src.assistant import provider
from src.observability.metrics import ApplicationMetrics, get_active_metrics, set_active_metrics

pytestmark = pytest.mark.no_infra


@pytest.fixture
def counters() -> Iterator[ApplicationMetrics]:
    previous = get_active_metrics()
    metrics = ApplicationMetrics()
    set_active_metrics(metrics)
    yield metrics
    set_active_metrics(previous)


class FakeModel:
    def __init__(self, answer: AIMessage | Exception) -> None:
        self.answer = answer

    def bind_tools(self, tools: list[type]) -> FakeModel:
        return self

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_fallback_records_every_attempt_and_does_not_double_count_token_details(
    monkeypatch: pytest.MonkeyPatch,
    counters: ApplicationMetrics,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class RateLimitError(Exception):
        status_code = 429

    answer = AIMessage(
        content="ok",
        usage_metadata={
            "input_tokens": 100,
            "output_tokens": 30,
            "total_tokens": 130,
            "input_token_details": {"cache_read": 40},
            "output_token_details": {"reasoning": 10},
        },
    )
    monkeypatch.setattr(
        provider,
        "available_models",
        lambda: [
            ("google", "primary", FakeModel(RateLimitError("secret-message-do-not-log"))),
            ("groq", "reserve", FakeModel(answer)),
        ],
    )
    result = asyncio.run(provider.call_model([], []))
    assert result.usage == provider.TokenUsage(100, 30)
    assert result.failed_attempts == 1 and result.fallback_used
    assert (
        counters.registry.get_sample_value(
            "kantano_assistant_llm_calls_total",
            {
                "provider": "google",
                "model": "primary",
                "result": "rate_limit",
                "fallback": "false",
                "usage": "missing",
            },
        )
        == 1
    )
    assert (
        counters.registry.get_sample_value(
            "kantano_assistant_llm_calls_total",
            {
                "provider": "groq",
                "model": "reserve",
                "result": "success",
                "fallback": "true",
                "usage": "reported",
            },
        )
        == 1
    )
    for direction, count in (("input", 100), ("output", 30)):
        assert (
            counters.registry.get_sample_value(
                "kantano_assistant_tokens_total",
                {
                    "provider": "groq",
                    "model": "reserve",
                    "direction": direction,
                },
            )
            == count
        )
    assert "secret-message-do-not-log" not in caplog.text


def test_missing_usage_is_not_zero_usage(
    monkeypatch: pytest.MonkeyPatch,
    counters: ApplicationMetrics,
) -> None:
    monkeypatch.setattr(
        provider,
        "available_models",
        lambda: [
            ("lmstudio", "local", FakeModel(AIMessage(content="ok"))),
        ],
    )
    assert asyncio.run(provider.call_model([], [])).usage is None
    assert (
        counters.registry.get_sample_value(
            "kantano_assistant_llm_calls_total",
            {
                "provider": "lmstudio",
                "model": "local",
                "result": "success",
                "fallback": "false",
                "usage": "missing",
            },
        )
        == 1
    )
    assert (
        counters.registry.get_sample_value(
            "kantano_assistant_tokens_total",
            {
                "provider": "lmstudio",
                "model": "local",
                "direction": "input",
            },
        )
        is None
    )


def test_cancelled_call_is_recorded_and_does_not_fall_back(
    monkeypatch: pytest.MonkeyPatch,
    counters: ApplicationMetrics,
) -> None:
    entered = asyncio.Event()

    class SlowModel(FakeModel):
        async def ainvoke(self, messages: list[Any]) -> AIMessage:
            entered.set()
            await asyncio.sleep(30)
            raise AssertionError("Must be cancelled")

    monkeypatch.setattr(
        provider,
        "available_models",
        lambda: [
            ("google", "primary", SlowModel(AIMessage(content=""))),
            ("groq", "reserve", FakeModel(AIMessage(content="unexpected"))),
        ],
    )

    async def exercise() -> None:
        call = asyncio.create_task(provider.call_model([], []))
        await entered.wait()
        call.cancel()
        with pytest.raises(asyncio.CancelledError):
            await call

    asyncio.run(exercise())
    assert (
        counters.registry.get_sample_value(
            "kantano_assistant_llm_calls_total",
            {
                "provider": "google",
                "model": "primary",
                "result": "cancelled",
                "fallback": "false",
                "usage": "missing",
            },
        )
        == 1
    )
    assert (
        counters.registry.get_sample_value(
            "kantano_assistant_llm_duration_seconds_count",
            {
                "provider": "groq",
                "model": "reserve",
            },
        )
        is None
    )


def test_sse_counts_http_requests_without_affecting_ordinary_api_latency() -> None:
    metrics = ApplicationMetrics()
    app = FastAPI()
    path = "/api/projects/{project_id}/assistant/conversations/{conversation_id}/runs"

    @app.post(path)
    @app.post(path + "/{run_id}/decision")
    async def stream() -> StreamingResponse:
        return StreamingResponse(
            iter(["event: done\ndata: {}\n\n"]), media_type="text/event-stream"
        )

    @app.get("/ordinary")
    async def ordinary() -> dict[str, bool]:
        return {"ok": True}

    metrics.instrument_fastapi(app)
    with TestClient(app) as client:
        assert client.post(path.format(project_id=1, conversation_id="chat")).status_code == 200
        assert (
            client.post(
                path.format(project_id=1, conversation_id="chat") + "/run/decision"
            ).status_code
            == 200
        )
        assert client.get("/ordinary").status_code == 200
    assert metrics.registry.get_sample_value("http_requests_total", {"status": "2xx"}) == 3
    assert (
        metrics.registry.get_sample_value(
            "http_request_duration_seconds_count",
            {
                "handler": "/ordinary",
            },
        )
        == 1
    )
    assert (
        metrics.registry.get_sample_value(
            "http_request_duration_seconds_count",
            {
                "handler": path,
            },
        )
        is None
    )
