"""Capabilities that shape one think step: a soft request budget and mid-step interrupts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability, CapabilityOrdering
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import AbstractToolset

from ..deps import Deps, DirectorDeps


@dataclass
class StepBudget(AbstractCapability[Deps]):
    """After `max_requests` model requests, offer no function tools, so the next reply must be end_turn.
    Wraps the assembled toolset, so it also covers tools that capabilities add (run_code, load_capability)."""

    max_requests: int

    def get_ordering(self) -> CapabilityOrdering:
        return CapabilityOrdering(position="outermost")

    def get_wrapper_toolset(self, toolset: AbstractToolset[Deps]) -> AbstractToolset[Deps]:
        return toolset.filtered(lambda ctx, _: ctx.usage.requests < self.max_requests)


@dataclass
class Interrupts(AbstractCapability[DirectorDeps]):
    """Deliver urgent game events and operator messages that arrive while the model works, after the current tool call."""

    async def after_tool_execute(self, ctx: RunContext[DirectorDeps], *, call: ToolCallPart, tool_def: ToolDefinition, args: Any, result: Any) -> Any:
        while ctx.deps.urgent:
            ctx.enqueue(ctx.deps.urgent.popleft(), priority="asap")
        return result
