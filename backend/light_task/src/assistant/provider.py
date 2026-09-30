import asyncio
import json
import logging
import ssl
from contextlib import nullcontext
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Any

import certifi
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_gigachat import GigaChat
from langchain_gigachat.utils.function_calling import convert_to_gigachat_tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from src.config import settings
from src.observability.metrics import record_assistant_llm_call

logger = logging.getLogger(__name__)
# The current API deployment runs one worker. Freemium allows one in-flight call.
_gigachat_lock = asyncio.Lock()


@lru_cache(maxsize=1)
def gigachat_model(credentials: str, model: str, scope: str, ca_bundle_file: Path) -> GigaChat:
    context = ssl.create_default_context(cafile=certifi.where())
    context.load_verify_locations(cafile=ca_bundle_file)
    # Reuse the SDK client so it caches and refreshes the OAuth access token.
    return GigaChat(
        credentials=credentials,
        model=model,
        scope=scope,
        base_url="https://api.giga.chat/v1",
        ssl_context=context,
        verify_ssl_certs=True,
        timeout=60,
        max_retries=0,
    )


def gigachat_tools(tools: list[type]) -> list[dict[str, Any]]:
    schemas = [convert_to_gigachat_tool(tool) for tool in tools]
    for schema in schemas:
        function = schema["function"]
        if function["name"] == "ExecutePlan":
            # GigaChat emits empty objects for free-form dicts. Transport plan
            # arguments as JSON, then restore the common contract before validation.
            args = function["parameters"]["properties"]["steps"]["items"]["properties"]["args"]
            args.clear()
            args.update(
                type="string",
                description="JSON-encoded object of the named tool's arguments, using its schema. "
                'Example: {"title":"Task", "column_id":"$column.column_id"}. '
                "Existing IDs are numbers; references to earlier creation steps are strings.",
            )
    return schemas


def gigachat_plan_arguments(message: BaseMessage, *, encode: bool) -> BaseMessage:
    if not isinstance(message, AIMessage) or not any(
        call["name"] == "ExecutePlan" for call in message.tool_calls
    ):
        return message
    converted = message.model_copy(deep=True)
    for call in converted.tool_calls:
        if call["name"] != "ExecutePlan":
            continue
        for step in call["args"].get("steps", []):
            if not isinstance(step, dict):
                continue
            args = step.get("args")
            if encode and isinstance(args, dict):
                step["args"] = json.dumps(args, ensure_ascii=False)
            elif not encode and isinstance(args, str):
                try:
                    step["args"] = json.loads(args)
                except json.JSONDecodeError:
                    # Let the existing tool validation report malformed arguments.
                    pass
    return converted


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int


def token_usage(message: BaseMessage) -> TokenUsage | None:
    usage = getattr(message, "usage_metadata", None)
    if not usage:
        return None
    counts = (usage.get("input_tokens"), usage.get("output_tokens"))
    if not all(isinstance(count, int) and count >= 0 for count in counts):
        return None
    return TokenUsage(input_tokens=counts[0], output_tokens=counts[1])


@dataclass(frozen=True)
class ModelAnswer:
    message: BaseMessage
    provider: str
    model: str
    fallback_used: bool
    duration_ms: int
    usage: TokenUsage | None = None
    failed_attempts: int = 0


def available_models() -> list[tuple[str, str, BaseChatModel]]:
    config = settings.assistant
    if config.mode == "local":
        return [
            (
                "lmstudio",
                config.local_model,
                ChatOpenAI(
                    model=config.local_model,
                    base_url=config.local_base_url,
                    api_key=SecretStr(config.local_api_key),
                    timeout=60,
                    max_retries=0,
                    stream_usage=True,
                ),
            )
        ]

    if config.cloud_provider == "ru":
        return [
            (
                "gigachat",
                config.gigachat_model,
                gigachat_model(
                    config.gigachat_credentials,
                    config.gigachat_model,
                    config.gigachat_scope,
                    config.gigachat_ca_bundle_file,
                ),
            )
        ]

    models: list[tuple[str, str, BaseChatModel]] = []
    if config.google_api_key:
        for model in (config.primary_model, config.google_fallback_model):
            models.append(
                (
                    "google",
                    model,
                    ChatGoogleGenerativeAI(
                        model=model,
                        google_api_key=config.google_api_key,
                        max_retries=0,
                        timeout=60,
                    ),
                )
            )
    if config.groq_api_key:
        models.append(
            (
                "groq",
                config.groq_model,
                ChatOpenAI(
                    model=config.groq_model,
                    base_url="https://api.groq.com/openai/v1",
                    api_key=SecretStr(config.groq_api_key),
                    timeout=60,
                    max_retries=0,
                    stream_usage=True,
                ),
            )
        )
    return models


async def call_model(
    messages: list[BaseMessage], tools: list[type], *, tool_choice: str | None = None
) -> ModelAnswer:
    models = available_models()
    if not models:
        raise RuntimeError("Assistant has no configured model")
    last_error: Exception | None = None
    call_started = perf_counter()
    for index, (provider, model_name, model) in enumerate(models):
        started = perf_counter()
        result = "success"
        usage: TokenUsage | None = None
        error_type: str | None = None
        try:
            choice = tool_choice
            if provider == "gigachat" and choice == "required":
                # GigaChat can force a named function, but not an arbitrary tool.
                if len(tools) != 1:
                    raise ValueError("GigaChat requires one tool for forced selection")
                choice = tools[0].__name__
            bound_tools = gigachat_tools(tools) if provider == "gigachat" else tools
            bound = (
                model.bind_tools(bound_tools, tool_choice=choice)
                if choice is not None
                else model.bind_tools(bound_tools)
            )
            model_messages = (
                [gigachat_plan_arguments(message, encode=True) for message in messages]
                if provider == "gigachat"
                else messages
            )
            async with _gigachat_lock if provider == "gigachat" else nullcontext():
                started = perf_counter()
                message = await bound.ainvoke(model_messages)
            if provider == "gigachat":
                message = gigachat_plan_arguments(message, encode=False)
            usage = token_usage(message)
            return ModelAnswer(
                message=message,
                provider=provider,
                model=model_name,
                fallback_used=index > 0,
                duration_ms=int((perf_counter() - call_started) * 1000),
                usage=usage,
                failed_attempts=index,
            )
        except asyncio.CancelledError:
            result = "cancelled"
            error_type = "CancelledError"
            raise
        except Exception as exc:
            error_type = type(exc).__name__
            code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
            result = "rate_limit" if code == 429 else "error"
            last_error = exc
        finally:
            duration = perf_counter() - started
            record_assistant_llm_call(
                provider,
                model_name,
                result,
                index > 0,
                duration,
                usage.input_tokens if usage else None,
                usage.output_tokens if usage else None,
            )
            logger.info(
                "assistant_llm_call",
                extra={
                    "provider": provider,
                    "model": model_name,
                    "result": result,
                    "error_type": error_type,
                    "fallback": index > 0,
                    "duration_ms": int(duration * 1000),
                    "usage_reported": usage is not None,
                    "input_tokens": usage.input_tokens if usage else None,
                    "output_tokens": usage.output_tokens if usage else None,
                },
            )
    raise RuntimeError("All assistant models failed") from last_error
