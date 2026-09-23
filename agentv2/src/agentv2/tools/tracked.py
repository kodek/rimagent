"""The values the situation report tracks for this game, which the agent chooses."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic_ai import RunContext, ToolFailed
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import AgentToolset, FunctionToolset

from ..bridge import BridgeError
from ..catalog import is_read_only
from ..deps import Deps
from ..world import SUMMARY, Tracked, Value, read_value

GUIDE = '''Each situation report has a "Tracked values" section: the recent values of what you track in this game. When you
read the same number at every step, track it with track_value instead (e.g. track_value(label="steel",
path="key_stocks.Steel")); untrack_value removes one.'''

toolset = FunctionToolset[Deps](id="tracked_values")


@toolset.tool
async def track_value(ctx: RunContext[Deps], label: str, path: str, method: str = SUMMARY, params: dict[str, Any] | None = None) -> dict[str, Value]:
    """Show a value in every situation report of this game, with its recent history. Returns its value now.

    Args:
        label: A short name, e.g. steel.
        path: A dotted path into the result, e.g. key_stocks.Steel or outside_storage.rotting; `#` counts a list, e.g. hostiles.#.
        method: A read-only RimBridge method (dotted, e.g. state.stocks); by default state.summary.
        params: The parameters of the method.
    """
    if not is_read_only(method):
        raise ToolFailed(f"{method} is not a read-only method; track only what state.*, map.* or defs.* methods return")
    tracked = Tracked(path=path, method=method, params=params or {})
    try:
        value = await read_value(ctx.deps.bridge, tracked)
    except BridgeError as e:
        raise ToolFailed(str(e)) from e
    tracked.record(value)
    ctx.deps.episode.tracked[label] = tracked
    return {label: value}


@toolset.tool
def untrack_value(ctx: RunContext[Deps], label: str) -> str:
    """Stop tracking a value.

    Args:
        label: The label of the tracked value.
    """
    if ctx.deps.episode.tracked.pop(label, None) is None:
        raise ToolFailed(f"no tracked value {label!r}; tracked: {sorted(ctx.deps.episode.tracked)}")
    return f"stopped tracking {label}"


@dataclass
class TrackedValues(AbstractCapability[Deps]):
    def get_instructions(self) -> str:
        return GUIDE

    def get_toolset(self) -> AgentToolset[Deps]:
        return toolset
