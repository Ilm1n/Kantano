from dataclasses import dataclass
from time import perf_counter

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from src.config import settings


@dataclass(frozen=True)
class ModelAnswer:
    message: BaseMessage
    provider: str
    model: str
    fallback_used: bool
    duration_ms: int


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
                ),
            )
        )
    return models


async def call_model(messages: list[BaseMessage], tools: list[type]) -> ModelAnswer:
    models = available_models()
    if not models:
        raise RuntimeError("Assistant has no configured model")
    last_error: Exception | None = None
    for index, (provider, model_name, model) in enumerate(models):
        started = perf_counter()
        try:
            message = await model.bind_tools(tools).ainvoke(messages)
            return ModelAnswer(
                message=message,
                provider=provider,
                model=model_name,
                fallback_used=index > 0,
                duration_ms=int((perf_counter() - started) * 1000),
            )
        except Exception as exc:
            last_error = exc
    raise RuntimeError("All assistant models failed") from last_error
