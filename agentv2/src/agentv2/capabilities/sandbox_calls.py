"""The tool calls that code in run_code makes: shown on the dashboard under their run_code call."""
from __future__ import annotations

import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from pydantic_ai import ModelRetry, RunContext, ToolReturn
from pydantic_ai.capabilities import (
    AbstractCapability,
    RawToolArgs,
    ValidatedToolArgs,
    WrapToolExecuteHandler,
)
from pydantic_ai.messages import ToolCallPart, ToolReturnPart
from pydantic_ai.tools import ToolDefinition

from ..deps import Deps
from ..events import ToolCall, ToolResult
from .telemetry import clip

RUN_CODE = "run_code"
_run_code_call: ContextVar[str | None] = ContextVar("run_code_call", default=None)


def outside_sandbox(ctx: RunContext[Any], tool_def: ToolDefinition) -> bool:
    return _run_code_call.get() is None


@dataclass
class SandboxCalls(AbstractCapability[Deps]):
    async def wrap_tool_execute(self, ctx: RunContext[Deps], *, call: ToolCallPart, tool_def: ToolDefinition,
                                args: ValidatedToolArgs, handler: WrapToolExecuteHandler) -> Any:
        parent = _run_code_call.get()
        if parent is None:
            if call.tool_name != RUN_CODE:
                return await handler(args)
            token = _run_code_call.set(call.tool_call_id)
            try:
                return await handler(args)
            finally:
                _run_code_call.reset(token)
        ctx.deps.emit(ToolCall(name=call.tool_name, args=args, id=call.tool_call_id, parent=parent))
        started = time.monotonic()
        try:
            result = await handler(args)
        except Exception as e:
            _emit_result(ctx, call, parent, started, ok=False, text=str(e))
            raise
        value = result.return_value if isinstance(result, ToolReturn) else result
        _emit_result(ctx, call, parent, started, ok=True, text=ToolReturnPart(call.tool_name, value).model_response_str())
        return result

    async def on_tool_validate_error(self, ctx: RunContext[Deps], *, call: ToolCallPart, tool_def: ToolDefinition,
                                     args: RawToolArgs, error: ValidationError | ModelRetry) -> ValidatedToolArgs:
        if parent := _run_code_call.get():
            ctx.deps.emit(ToolCall(name=call.tool_name, args=call.args_as_dict(), id=call.tool_call_id, parent=parent))
            _emit_result(ctx, call, parent, time.monotonic(), ok=False, text=str(error))
        raise error


def _emit_result(ctx: RunContext[Deps], call: ToolCallPart, parent: str, started: float, *, ok: bool, text: str) -> None:
    ctx.deps.emit(ToolResult(name=call.tool_name, id=call.tool_call_id, parent=parent, ok=ok, text=clip(text),
                             elapsed=round(time.monotonic() - started, 2)))
