import asyncio
import logging
from dataclasses import dataclass
from time import perf_counter

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from src.config import settings
from src.observability.metrics import record_assistant_llm_call

logger = logging.getLogger(__name__)


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
            bound = (
                model.bind_tools(tools, tool_choice=tool_choice)
                if tool_choice is not None
                else model.bind_tools(tools)
            )
            message = await bound.ainvoke(messages)
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
