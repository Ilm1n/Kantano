import asyncio
import json
import logging
import ssl
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Any

import certifi
import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_gigachat import GigaChat
from langchain_gigachat.utils.function_calling import convert_to_gigachat_tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from src.assistant.plans import plan_examples
from src.assistant.tool_schemas import ToolSchema
from src.cache.redis import RedisCache
from src.config import settings
from src.observability.metrics import record_assistant_llm_call

logger = logging.getLogger(__name__)
# The current API deployment runs one worker. Freemium allows one in-flight call.
_gigachat_lock = asyncio.Lock()
MODEL_CALL_TIMEOUT = 120
QUOTA_COOLDOWN_SECONDS = 3600
MAX_RATE_LIMIT_WAIT_SECONDS = 5


@lru_cache(maxsize=4)
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


def gigachat_tools(tools: list[ToolSchema]) -> list[dict[str, Any]]:
    schemas = [deepcopy(convert_to_gigachat_tool(tool)) for tool in tools]
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
            examples = plan_examples()
            for example in examples:
                for step in example["params"]["steps"]:
                    step["args"] = json.dumps(step["args"], ensure_ascii=False)
            function["few_shot_examples"] = examples
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
                model_name,
                gigachat_model(
                    config.gigachat_credentials,
                    model_name,
                    config.gigachat_scope,
                    config.gigachat_ca_bundle_file,
                ),
            )
            for model_name in config.gigachat_models or [config.gigachat_model]
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


def quota_key(model: str) -> str:
    account = sha256(settings.assistant.gigachat_credentials.encode()).hexdigest()[:16]
    return f"cache:v1:assistant:quota:{account}:{model}"


def error_status(exc: Exception) -> int | None:
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    return code if isinstance(code, int) else None


async def call_model(
    messages: list[BaseMessage],
    tools: list[ToolSchema],
    *,
    tool_choice: str | None = None,
    preferred_model: str | None = None,
    quota_cache: RedisCache | None = None,
) -> ModelAnswer:
    models = available_models()
    if not models:
        raise RuntimeError("Assistant has no configured model")
    candidates = list(enumerate(models))
    if preferred_model is not None and models[0][0] == "gigachat":
        start = next((i for i, (_, name, _) in candidates if name == preferred_model), 0)
        candidates = candidates[start:]
    call_started = perf_counter()
    failed_attempts = 0
    last_error: Exception | None = None
    slot = _gigachat_lock if models[0][0] == "gigachat" else nullcontext()
    timeout = MODEL_CALL_TIMEOUT if models[0][0] == "gigachat" else None
    async with asyncio.timeout(timeout), slot:
        for index, (provider, model_name, model) in candidates:
            if provider == "gigachat" and quota_cache is not None:
                cached = await quota_cache.get(quota_key(model_name), cache_name="assistant_quota")
                if cached.value is not None:
                    continue
            # 429 affects the account, so retry this model once without changing it.
            for attempt in range(2):
                try:
                    message, usage = await invoke_model(
                        messages, tools, provider, model_name, model, tool_choice, index > 0
                    )
                    return ModelAnswer(
                        message=message,
                        provider=provider,
                        model=model_name,
                        fallback_used=index > 0,
                        duration_ms=int((perf_counter() - call_started) * 1000),
                        usage=usage,
                        failed_attempts=failed_attempts,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    failed_attempts += 1
                    last_error = exc
                    if provider != "gigachat":
                        break
                    code = error_status(exc)
                    if code == 429:
                        delay = getattr(exc, "retry_after", 1) or 1
                        if attempt == 0 and 0 <= delay <= MAX_RATE_LIMIT_WAIT_SECONDS:
                            await asyncio.sleep(delay)
                            continue
                        raise
                    if code == 402:
                        if quota_cache is not None:
                            await quota_cache.set(
                                quota_key(model_name),
                                b"exhausted",
                                ttl_seconds=QUOTA_COOLDOWN_SECONDS,
                                cache_name="assistant_quota",
                            )
                        break
                    if (code is not None and 500 <= code < 600) or isinstance(
                        exc, (httpx.TransportError, TimeoutError)
                    ):
                        break
                    # Authentication, invalid schemas and programming errors are not quotas.
                    raise
    raise RuntimeError("All assistant models are unavailable") from last_error


async def invoke_model(
    messages: list[BaseMessage],
    tools: list[ToolSchema],
    provider: str,
    model_name: str,
    model: BaseChatModel,
    tool_choice: str | None,
    fallback: bool,
) -> tuple[BaseMessage, TokenUsage | None]:
    started = perf_counter()
    result = "success"
    usage: TokenUsage | None = None
    error_type: str | None = None
    status_code: int | None = None
    try:
        choice = tool_choice
        if provider == "gigachat" and choice == "required":
            # GigaChat can force a named function, but not an arbitrary tool.
            if len(tools) != 1:
                raise ValueError("GigaChat requires one tool for forced selection")
            tool = tools[0]
            choice = tool["function"]["name"] if isinstance(tool, dict) else tool.__name__
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
        message = await bound.ainvoke(model_messages)
        if provider == "gigachat":
            message = gigachat_plan_arguments(message, encode=False)
        usage = token_usage(message)
        return message, usage
    except asyncio.CancelledError:
        result = "cancelled"
        error_type = "CancelledError"
        raise
    except Exception as exc:
        error_type = type(exc).__name__
        code = error_status(exc)
        status_code = code
        result = "rate_limit" if code == 429 else "error"
        raise
    finally:
        duration = perf_counter() - started
        record_assistant_llm_call(
            provider,
            model_name,
            result,
            fallback,
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
                "fallback": fallback,
                "error_status": status_code,
                "duration_ms": int(duration * 1000),
                "usage_reported": usage is not None,
                "input_tokens": usage.input_tokens if usage else None,
                "output_tokens": usage.output_tokens if usage else None,
            },
        )
