"""Layouts in one ui.build_many call."""
from dataclasses import dataclass
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import FunctionToolset

tools = FunctionToolset()


@tools.tool
async def room(ctx: RunContext, x: int, z: int, w: int, h: int, door: str = "S", stuff: str = "WoodLog", beds: int = 0,
               bed_rot: str = "E", dry_run: bool = True) -> dict[str, Any]:
    """A walled room with one door and optional beds along the west wall, in one ui.build_many call. Check a dry run first.

    Args:
        x: Minimum x of the outer wall.
        z: Minimum z of the outer wall.
        w: Outer width in cells.
        h: Outer height in cells.
        door: The wall with the door: N, S, E or W.
        stuff: Material, e.g. WoodLog or BlocksGranite.
        beds: Beds to place inside.
        bed_rot: Bed rotation N, E, S or W.
        dry_run: Report placed and failed cells without building.
    """
    door_at = {"S": [x + w // 2, z], "N": [x + w // 2, z + h - 1], "W": [x, z + h // 2], "E": [x + w - 1, z + h // 2]}[door.upper()]
    ops = [{"def": "Wall", "rect": [x, z, w, h], "stuff": stuff}, {"def": "Door", "at": door_at, "stuff": stuff}]
    ops += [{"def": "Bed", "at": [x + 1, z + 1 + 2 * i], "rot": bed_rot, "stuff": stuff} for i in range(beds)]
    result = await ctx.deps.bridge.call("ui.build_many", {"ops": [{**op, "dry_run": dry_run} for op in ops]})
    return {"door": door_at, "results": result}


@dataclass
class Construction(AbstractCapability):
    def get_toolset(self):
        return tools
