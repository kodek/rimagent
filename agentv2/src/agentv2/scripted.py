"""A scripted stand-in for the LLM (streaming and non-streaming), for tests and offline commands."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ThinkingPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaThinkingCalls, DeltaThinkingPart, DeltaToolCall, DeltaToolCalls, FunctionModel

Responder = Callable[[list[ModelMessage], AgentInfo], ModelResponse]


def scripted_model(respond: Responder) -> FunctionModel:
    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str | DeltaToolCalls | DeltaThinkingCalls]:
        for i, part in enumerate(respond(messages, info).parts):
            match part:
                case ThinkingPart(content=text):
                    yield {i: DeltaThinkingPart(content=text)}
                case TextPart(content=text):
                    yield text
                case ToolCallPart():
                    args = part.args if isinstance(part.args, str) else json.dumps(part.args or {})
                    yield {i: DeltaToolCall(name=part.tool_name, json_args=args, tool_call_id=part.tool_call_id)}

    return FunctionModel(respond, stream_function=stream)


def call(name: str, args: dict[str, Any] | str | None = None) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(name, args or {})])


def code(source: str) -> ModelResponse:
    return call("run_code", {"code": source})
