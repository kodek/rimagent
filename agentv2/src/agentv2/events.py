"""Bus events: one model per kind. This is the contract between the producers and the dashboard (dashboard/index.html).
`Deps.emit` adds `stream` (play, improve or reflect) to the events of a run."""
from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict


class Event(BaseModel):
    KIND: ClassVar[str]
    EPHEMERAL: ClassVar[bool] = False

    def payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class Status(Event):
    """game.status and the runner's own state; merged into Bus.state."""

    KIND = "status"
    model_config = ConfigDict(extra="allow")

    phase: str | None = None
    episode: int | None = None
    seed: str | None = None
    deaths: int | None = None
    raids: int | None = None
    next_wake_tick: int | None = None
    model_speed: int | None = None
    steward: bool | None = None
    sandbox: bool | None = None


class Log(Event):
    KIND = "log"
    text: str


class Error(Event):
    KIND = "error"
    text: str


class ThinkStart(Event):
    KIND = "think_start"
    trigger: str
    step: int
    urgent: bool
    prompt_chars: int


class ThinkEnd(Event):
    KIND = "think_end"
    notes: str
    elapsed: float
    calls: int | None = None
    requests: int | None = None
    tokens: int | None = None
    wake: dict[str, Any] | None = None
    end_episode: str | None = None


class Delta(Event):
    KIND = "delta"
    EPHEMERAL = True
    part: str
    text: str


class Reasoning(Event):
    KIND = "reasoning"
    text: str


class Assistant(Event):
    KIND = "assistant"
    text: str


class ToolCall(Event):
    KIND = "tool_call"
    name: str
    args: dict[str, Any]
    id: str


class ToolResult(Event):
    KIND = "tool_result"
    name: str | None
    id: str
    ok: bool
    text: str
    elapsed: float


class Context(Event):
    KIND = "context"
    used_tokens: int
    window_tokens: int
    fraction: float


class Harness(Event):
    """A Pydantic AI Harness capability event."""

    KIND = "harness"
    kind: str
    data: dict[str, Any]


class Ledger(Event):
    """One game ledger event, as RimBridge sends it."""

    KIND = "ledger"
    model_config = ConfigDict(extra="allow")


class WatcherAlert(Event):
    KIND = "watcher"
    name: str
    alert: str
    wake: bool


class WatcherAction(Event):
    KIND = "watcher"
    name: str
    action: str
    params: dict[str, Any]
    note: str | None
    ok: bool
    result: Any


class WatcherFailed(Event):
    KIND = "watcher"
    name: str
    error: str


class BrainChange(Event):
    KIND = "brain_change"
    kind: str
    action: str
    name: str | None = None
    sha: str | None = None


class EpisodeStart(Event):
    KIND = "episode_start"
    episode: int
    seed: str
    sandbox: bool | None = None
    resumed: bool | None = None
    day: int | None = None
    restored_messages: int | None = None


class EpisodeEnd(Event):
    KIND = "episode_end"
    episode: int
    score: float
    reason: str
    assisted: bool
    brain_sha: str
    days: int


class Situation(Event):
    KIND = "situation"
    trigger: str
    changes: str
    day: int | None
    hour: int | None
    chars: int


class Operator(Event):
    KIND = "operator"
    text: str


class Reply(Event):
    KIND = "reply"
    text: str
