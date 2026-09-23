"""Forward each run's event stream to the bus for the dashboard: live thinking, tool calls, Harness events."""
from __future__ import annotations

import json
import time
from collections.abc import AsyncIterable
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import ProcessEventStream
from pydantic_ai.messages import (
    AgentStreamEvent,
    CapabilityEvent,
    EnqueuedMessagesEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    OutputToolCallEvent,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolReturnPart,
)
from pydantic_ai_harness.compaction import ContextUsageEvent
from pydantic_ai_harness.filesystem import DirectoryCreatedEvent, FileEditedEvent, FileWrittenEvent

from ..brain import BrainLayout
from ..deps import Deps

RESULT_CLIP = 3000
DELTA_FLUSH_S = 0.15
QUIET = {"step_persistence.snapshot_saved", "file_system.file_read", "file_system.directory_listed", "file_system.files_searched"}


def clip(text: str, limit: int = RESULT_CLIP) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n…(clipped {len(text) - limit} chars for the log; the model got all of it)"


def telemetry() -> ProcessEventStream[Deps]:
    return ProcessEventStream(_forward)


async def _forward(ctx: RunContext[Deps], stream: AsyncIterable[AgentStreamEvent]) -> None:
    forwarder = _Forwarder(ctx.deps)
    async for event in stream:
        forwarder.handle(event)
    forwarder.flush()


class _Forwarder:
    def __init__(self, deps: Deps) -> None:
        self.deps = deps
        self._started: dict[str, float] = {}
        self._pending: dict[str, str] = {}
        self._flushed = 0.0

    def handle(self, event: Any) -> None:
        emit = self.deps.emit
        match event:
            case PartStartEvent(part=ThinkingPart(content=text)) | PartStartEvent(part=TextPart(content=text)) if text:
                self._delta("thinking" if isinstance(event.part, ThinkingPart) else "text", text)
            case PartDeltaEvent(delta=ThinkingPartDelta(content_delta=text)) if text:
                self._delta("thinking", text)
            case PartDeltaEvent(delta=TextPartDelta(content_delta=text)) if text:
                self._delta("text", text)
            case PartEndEvent(part=ThinkingPart(content=text)):
                self.flush()
                if text.strip():
                    emit("reasoning", {"text": text})
            case PartEndEvent(part=TextPart(content=text)):
                self.flush()
                if text.strip():
                    emit("assistant", {"text": text})
            case FunctionToolCallEvent(part=part) | OutputToolCallEvent(part=part):
                self._started[part.tool_call_id] = time.monotonic()
                emit("tool_call", {"name": part.tool_name, "args": part.args_as_dict(), "id": part.tool_call_id})
            case FunctionToolResultEvent(part=part):
                ok = isinstance(part, ToolReturnPart) and part.outcome != "failed"
                text = part.model_response_str() if isinstance(part, ToolReturnPart) else part.model_response()
                elapsed = time.monotonic() - self._started.pop(part.tool_call_id, time.monotonic())
                emit("tool_result", {"name": part.tool_name, "id": part.tool_call_id, "ok": ok, "text": clip(text), "elapsed": round(elapsed, 2)})
            case EnqueuedMessagesEvent():
                emit("log", {"text": "delivered to the model mid-step"})
            case ContextUsageEvent():
                emit("context", {"used_tokens": event.used_tokens, "window_tokens": event.window_tokens, "fraction": event.fraction})
            case FileWrittenEvent() | FileEditedEvent() | DirectoryCreatedEvent() if event.capability_id == "brain_files":
                action = {FileWrittenEvent: "write", FileEditedEvent: "edit", DirectoryCreatedEvent: "mkdir"}[type(event)]
                emit("brain_change", {"kind": BrainLayout.kind_of(event.path), "name": event.path, "action": action})
            case CapabilityEvent(kind=kind) if kind not in QUIET:
                emit("harness", {"kind": kind, "data": _payload(event)})
            case _:
                pass

    def _delta(self, part: str, text: str) -> None:
        self._pending[part] = self._pending.get(part, "") + text
        if time.monotonic() - self._flushed >= DELTA_FLUSH_S:
            self.flush()

    def flush(self) -> None:
        for part, text in self._pending.items():
            if text:
                self.deps.emit("delta", {"part": part, "text": text}, ephemeral=True)
        self._pending.clear()
        self._flushed = time.monotonic()


def _payload(event: CapabilityEvent) -> dict[str, Any]:
    skip = {"kind", "capability_id", "event_kind"}
    data = {k: v for k, v in vars(event).items() if k not in skip and not k.startswith("_")}
    return json.loads(json.dumps(data, default=str))
