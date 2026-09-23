"""The director session: one continuous conversation per game, restored from StepPersistence after a restart."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from pydantic_ai import Agent, RunUsage, capture_run_messages
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.messages import ModelMessage
from pydantic_ai_harness.step_persistence import SqliteStepStore, continue_run

from .brain import Brain
from .deps import DirectorDeps
from .events import Error, ThinkEnd, ThinkStart
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
    history: list[ModelMessage] = field(default_factory=list, init=False)
    notes: list[str] = field(default_factory=list, init=False)
    active: DirectorDeps | None = field(default=None, init=False)
    step_no: int = field(default=0, init=False)

    async def restore(self, colony: str) -> int:
        runs = await self.steps.list_runs(conversation_id=colony)
        self.history = await continue_run(self.steps, run_id=runs[-1].run_id) if runs else []
        self.notes = []
        return len(self.history)

    def reset(self) -> None:
        self.history, self.notes = [], []

    async def step(self, prompt: str, deps: DirectorDeps, wake: Wake) -> StepOutcome:
        self.step_no += 1
        deps.emit(ThinkStart(trigger=wake.trigger, step=self.step_no, urgent=wake.urgent, prompt_chars=len(prompt)))
        started = time.monotonic()
        usage: RunUsage | None = None
        self.active = deps
        with capture_run_messages() as captured:
            try:
                result = await run_agent(self.agent, prompt, deps, self.brain, max_requests=self.max_requests, history=self.history,
                                         conversation_id=deps.episode.colony)
            except AgentRunError as e:
                self.history = list(captured) or self.history
                error = f"{type(e).__name__}: {e}"
                deps.bus.emit(Error(text=f"think step failed: {error}"))
                outcome = StepOutcome(notes=f"(step failed: {error})", error=error)
            else:
                self.history = result.all_messages()
                outcome, usage = _outcome(result.output), result.usage
            finally:
                self.active = None
        self.notes.append(outcome.notes)
        deps.emit(ThinkEnd(notes=outcome.notes, elapsed=round(time.monotonic() - started, 1), calls=usage.tool_calls if usage else None,
                           requests=usage.requests if usage else None, tokens=usage.total_tokens if usage else None,
                           wake=outcome.end.model_dump() if outcome.end else None, end_episode=outcome.episode_end))
        return outcome

    def interrupt(self, text: str) -> bool:
        """Deliver `text` to the running step; False when no step runs."""
        if self.active is None:
            return False
        self.active.urgent.append(text)
        return True


def _outcome(output: TurnEnd | EpisodeEnd) -> StepOutcome:
    match output:
        case TurnEnd() as end:
            return StepOutcome(notes=end.notes, end=end)
        case EpisodeEnd(reason=reason):
            return StepOutcome(notes=reason, episode_end=reason)
