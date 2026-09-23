"""Method access from the caller's MethodPolicy: hide the rw_* tools it may not use and block such rpc() calls."""
from __future__ import annotations

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability, PrepareTools
from pydantic_ai.tools import ToolDefinition
from pydantic_ai_harness.guardrails import GuardrailResult, ToolCallInfo, ToolGuardrail

from ..deps import Deps
from ..tools.bridge import bridge_method


def _visible(ctx: RunContext[Deps], tool_defs: list[ToolDefinition]) -> list[ToolDefinition]:
    policy = ctx.deps.policy
    return [t for t in tool_defs if (method := bridge_method(t)) is None or policy.refusal(method) is None]


def _guard(ctx: RunContext[Deps], call: ToolCallInfo) -> GuardrailResult:
    refusal = ctx.deps.policy.refusal(str(call.args.get("method", "")))
    return GuardrailResult.block(refusal) if refusal else GuardrailResult.allow()


def method_access() -> list[AbstractCapability[Deps]]:
    return [PrepareTools(_visible), ToolGuardrail(guard=_guard, tools=["rpc"])]
