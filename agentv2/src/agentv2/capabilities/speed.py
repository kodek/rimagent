"""Remember the game speed the director set, so the runner keeps it after the step."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability, ValidatedToolArgs
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import ToolDefinition

from ..deps import DirectorDeps
from ..tools.bridge import bridge_method


@dataclass
class TrackSpeed(AbstractCapability[DirectorDeps]):
    async def after_tool_execute(self, ctx: RunContext[DirectorDeps], *, call: ToolCallPart, tool_def: ToolDefinition,
                                 args: ValidatedToolArgs, result: Any) -> Any:
        match bridge_method(tool_def):
            case "game.speed":
                ctx.deps.turn.model_speed = int(args.get("speed", 1))
            case "game.pause" if args.get("paused", True):
                ctx.deps.turn.model_speed = 0
        return result
