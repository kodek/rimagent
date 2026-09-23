"""Method access from the caller's MethodPolicy: hide the rw_* tools it may not use, also from run_code."""
from __future__ import annotations

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability, PrepareTools
from pydantic_ai.tools import ToolDefinition

from ..deps import Deps
from ..tools.bridge import bridge_method


def _visible(ctx: RunContext[Deps], tool_defs: list[ToolDefinition]) -> list[ToolDefinition]:
    policy = ctx.deps.policy
    return [t for t in tool_defs if (method := bridge_method(t)) is None or policy.refusal(method) is None]


def method_access() -> AbstractCapability[Deps]:
    return PrepareTools(_visible)
