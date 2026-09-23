"""The model: any OpenAI-compatible Chat Completions server, with the server's own sampling defaults. `llm.thinking`
switches Qwen thinking through the chat template; unset, the server decides. `llm.timeout_s` bounds one request."""
from __future__ import annotations

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from .config import LLMSettings


def build_model(llm: LLMSettings) -> OpenAIChatModel:
    settings = ModelSettings(timeout=llm.timeout_s)
    if llm.thinking is not None:
        settings["extra_body"] = {"chat_template_kwargs": {"enable_thinking": llm.thinking}}
    return OpenAIChatModel(
        llm.model,
        provider=OpenAIProvider(base_url=llm.base_url, api_key=llm.api_key),
        profile=OpenAIModelProfile(openai_chat_supports_multiple_system_messages=False),
        settings=settings,
    )
