"""Run one agent to its output through `agent.iter`, and run it again without the agent-authored capabilities if they break it."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from pydantic_ai import Agent, AgentRun, AgentRunResult, UsageLimits
from pydantic_ai.exceptions import UserError
from pydantic_ai.messages import ModelMessage

from .brain import AUTHORED, Brain
from .deps import Deps
from .events import Error


async def run_agent[D: Deps, O](agent: Agent[D, O], prompt: str, deps: D, brain: Brain, *, max_requests: int, history: Sequence[ModelMessage] = (),
                                conversation_id: str | None = None, on_start: Callable[[AgentRun[D, Any]], None] | None = None) -> AgentRunResult[O]:
    limits = UsageLimits(request_limit=max_requests + 5)

    async def attempt(authored: bool) -> AgentRunResult[O]:
        async with agent.iter(prompt, deps=deps, message_history=list(history) or None, conversation_id=conversation_id,
                              usage_limits=limits, metadata={AUTHORED: authored}) as run:
            if on_start:
                on_start(run)
            async for _ in run:
                pass
        assert run.result is not None, "the run ended without a result"
        return run.result

    try:
        return await attempt(authored=True)
    except UserError as e:
        if not brain.has_authored():
            raise
        deps.bus.emit(Error(text=f"{deps.role.name}: an authored capability broke the run; running without authored capabilities: {e}"))
        return await attempt(authored=False)
