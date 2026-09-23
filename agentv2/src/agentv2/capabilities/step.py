"""A soft request budget for one run: after `max_requests` requests, only the output tools are offered."""
from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai.capabilities import AbstractCapability, CapabilityOrdering
from pydantic_ai.toolsets import AbstractToolset

from ..deps import Deps


@dataclass
class StepBudget(AbstractCapability[Deps]):
    """Wraps the assembled toolset, so it also covers tools that capabilities add (run_code, load_capability)."""

    max_requests: int

    def get_ordering(self) -> CapabilityOrdering:
        return CapabilityOrdering(position="outermost")

    def get_wrapper_toolset(self, toolset: AbstractToolset[Deps]) -> AbstractToolset[Deps]:
        return toolset.filtered(lambda ctx, _: ctx.usage.requests < self.max_requests)
