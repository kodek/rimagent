"""The director session: one continuous conversation per game. StepPersistence keeps it, so each step reads it back
from the store, also after a failed or cancelled step and after a restart. Urgent news reaches the running step."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent, AgentRun, RunUsage
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai_harness.step_persistence import SqliteStepStore

from .brain import Brain
from .deps import DirectorDeps
from .events import Error, ThinkEnd, ThinkStart
from .roles import DIRECTOR
from .running import run_agent
from .tools.turn import EpisodeEnd, TurnEnd
from .wake import Wake


@dataclass
class StepOutcome:
    notes: str
    end: TurnEnd | None = None
    episode_end: str | None = None
    error: str | None = None


def urgent_message(items: list[str]) -> str:
    return "## URGENT, happened while you were working\n" + "\n".join(f"- {i}" for i in items) + "\nDeal with these first, then continue."


def operator_message(text: str) -> str:
    return "## Message from the human operator\nAnswer it now with reply_to_operator, then continue.\n- " + text


@dataclass
class DirectorSession:
    agent: Agent[DirectorDeps, TurnEnd | EpisodeEnd]
    steps: SqliteStepStore
    brain: Brain
    max_requests: int
    active: AgentRun[DirectorDeps, Any] | None = field(default=None, init=False)
    step_no: int = field(default=0, init=False)

    async def history(self, colony: str) -> list[ModelMessage]:
        for run in reversed(await self.steps.list_runs(conversation_id=colony)):
            if run.agent_name == DIRECTOR.name and (snapshot := await self.steps.latest_snapshot(run_id=run.run_id, include_interrupted=True)):
                return list(snapshot.messages)
        return []

    async def notes(self, colony: str) -> list[str]:
        """The notes of the end_turn calls the director still has in its conversation."""
        return [str(part.args_as_dict().get("notes", "")) for m in await self.history(colony) if isinstance(m, ModelResponse)
                for part in m.parts if isinstance(part, ToolCallPart) and part.tool_name == "end_turn"]

    async def step(self, prompt: str, deps: DirectorDeps, wake: Wake) -> StepOutcome:
        self.step_no += 1
        deps.emit(ThinkStart(trigger=wake.trigger, step=self.step_no, urgent=wake.urgent, prompt_chars=len(prompt)))
        started = time.monotonic()
        usage: RunUsage | None = None
        try:
            result = await run_agent(self.agent, prompt, deps, self.brain, max_requests=self.max_requests,
                                     history=await self.history(deps.episode.colony), conversation_id=deps.episode.colony, on_start=self._started)
        except AgentRunError as e:
            error = f"{type(e).__name__}: {e}"
            deps.bus.emit(Error(text=f"think step failed: {error}"))
            outcome = StepOutcome(notes=f"(step failed: {error})", error=error)
        else:
            outcome, usage = _outcome(result.output), result.usage
        finally:
            self.active = None
        deps.emit(ThinkEnd(notes=outcome.notes, elapsed=round(time.monotonic() - started, 1), calls=usage.tool_calls if usage else None,
                           requests=usage.requests if usage else None, tokens=usage.total_tokens if usage else None,
                           wake=outcome.end.model_dump() if outcome.end else None, end_episode=outcome.episode_end))
        return outcome

    def interrupt(self, text: str) -> bool:
        """Deliver `text` to the running step; False when no step runs."""
        if self.active is None:
            return False
        self.active.enqueue(text)
        return True

    def cancel(self) -> None:
        if self.active is not None:
            self.active.cancel()

    def _started(self, run: AgentRun[DirectorDeps, Any]) -> None:
        self.active = run


def _outcome(output: TurnEnd | EpisodeEnd) -> StepOutcome:
    match output:
        case TurnEnd() as end:
            return StepOutcome(notes=end.notes, end=end)
        case EpisodeEnd(reason=reason):
            return StepOutcome(notes=reason, episode_end=reason)
