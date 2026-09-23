"""One tool per RimBridge method (`rw_<group>_<name>`), built from the live catalog on every step."""
from __future__ import annotations

import json
import re
from typing import Any

from pydantic_ai import RunContext, ToolFailed
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.toolsets.abstract import ToolsetTool
from pydantic_core import SchemaValidator, core_schema

from ..bridge import BridgeError
from ..catalog import Method
from ..deps import Deps

_JSON_SCALAR = re.compile(r"^(true|false|null|-?\d+(\.\d+)?)$")


def coerce(value: Any) -> Any:
    """Models often send nested JSON as strings ("[97, 98]", "true", '{"a": 1}'). Undo that where it is unambiguous."""
    if isinstance(value, str):
        text = value.strip()
        if text[:1] in ("[", "{", '"') or _JSON_SCALAR.match(text):
            try:
                return coerce(json.loads(text))
            except json.JSONDecodeError:
                return value
        return value
    if isinstance(value, list):
        return [coerce(v) for v in value]
    if isinstance(value, dict):
        return {k: coerce(v) for k, v in value.items()}
    return value


ARGS_VALIDATOR = SchemaValidator(core_schema.no_info_before_validator_function(
    coerce, core_schema.dict_schema(core_schema.str_schema(), core_schema.any_schema())))


def visible(method: Method, deps: Deps) -> bool:
    if method.dev and not deps.episode.sandbox:
        return False
    return deps.stream == "play" or method.read_only


class BridgeToolset(AbstractToolset[Deps]):
    @property
    def id(self) -> str:
        return "rimbridge"

    async def get_tools(self, ctx: RunContext[Deps]) -> dict[str, ToolsetTool[Deps]]:
        tools = {}
        for method in ctx.deps.catalog:
            if not visible(method, ctx.deps):
                continue
            tool_def = ToolDefinition(
                name=method.tool_name,
                parameters_json_schema=method.schema,
                description=f"[RimBridge {method.name}] {method.doc}"[:1500],
                sequential=not method.read_only,
            )
            tools[method.tool_name] = ToolsetTool(toolset=self, tool_def=tool_def, max_retries=3, args_validator=ARGS_VALIDATOR)
        return tools

    async def call_tool(self, name: str, tool_args: dict[str, Any], ctx: RunContext[Deps], tool: ToolsetTool[Deps]) -> Any:
        method = next(m.name for m in ctx.deps.catalog if m.tool_name == name)
        try:
            result = await ctx.deps.bridge.call(method, tool_args)
        except BridgeError as e:
            raise ToolFailed(str(e)) from e
        if method == "game.speed":
            ctx.deps.turn.model_speed = int(tool_args.get("speed", 1))
        elif method == "game.pause" and tool_args.get("paused", True):
            ctx.deps.turn.model_speed = 0
        return result
