"""The model: any OpenAI-compatible Chat Completions server, with the server's own sampling and thinking defaults."""
from __future__ import annotations

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider

from .config import LLMSettings


def build_model(llm: LLMSettings) -> OpenAIChatModel:
    return OpenAIChatModel(
        llm.model,
        provider=OpenAIProvider(base_url=llm.base_url, api_key=llm.api_key),
        profile=OpenAIModelProfile(openai_chat_supports_multiple_system_messages=False),
    )
