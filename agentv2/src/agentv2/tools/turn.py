"""How a step ends (output functions) and the operator channel."""
from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_ai import RunContext, ToolOutput
from pydantic_ai.toolsets import FunctionToolset

from ..deps import Deps


class TurnEnd(BaseModel):
    notes: str
    wake_in_hours: float | None = None
    wake_on: list[str] = Field(default_factory=list)


class EpisodeEnd(BaseModel):
    reason: str


class Finished(BaseModel):
    notes: str


def end_turn(notes: str, wake_in_hours: float | None = None, wake_on: list[str] | None = None) -> TurnEnd:
    """Finish this think step. The game resumes.

    Args:
        notes: 1-3 sentences: what you did and what to check next.
        wake_in_hours: In-game hours until the next scheduled step.
        wake_on: Ledger event kinds that should wake you early, e.g. letter, incident, quest, day.
    """
    return TurnEnd(notes=notes, wake_in_hours=wake_in_hours, wake_on=wake_on or [])


def end_episode(reason: str) -> EpisodeEnd:
    """Declare this game over (colony lost or hopeless). Starts the episode reflection and a new game.

    Args:
        reason: Why the game is over.
    """
    return EpisodeEnd(reason=reason)


def finish(notes: str) -> Finished:
    """Finish this pass.

    Args:
        notes: One paragraph: what you changed in the brain and why.
    """
    return Finished(notes=notes)


PLAY_OUTPUT: list[ToolOutput[TurnEnd | EpisodeEnd]] = [ToolOutput(end_turn, name="end_turn"), ToolOutput(end_episode, name="end_episode")]
PASS_OUTPUT: list[ToolOutput[Finished]] = [ToolOutput(finish, name="finish")]

operator = FunctionToolset[Deps](id="operator")


@operator.tool
def reply_to_operator(ctx: RunContext[Deps], text: str) -> str:
    """Reply to the human operator watching the dashboard. Answer every operator message before you continue.

    Args:
        text: Your reply, one or two sentences.
    """
    ctx.deps.turn.replies.append(text)
    ctx.deps.emit("reply", {"text": text})
    return "delivered to the operator"
