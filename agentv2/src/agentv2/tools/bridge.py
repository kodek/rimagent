"""One tool per RimBridge method (`rw_<group>_<name>`), built from the live catalog on every step."""
from __future__ import annotations

from typing import Any

from pydantic_ai import RunContext, ToolFailed
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.toolsets.abstract import ToolsetTool
from pydantic_core import SchemaValidator, core_schema

from ..bridge import BridgeError
from ..catalog import bridge_params
from ..deps import Deps

METHOD = "rimbridge"
ARGS_VALIDATOR = SchemaValidator(core_schema.dict_schema(core_schema.str_schema(), core_schema.any_schema()))


def bridge_method(tool_def: ToolDefinition) -> str | None:
    return (tool_def.metadata or {}).get(METHOD)


class BridgeToolset(AbstractToolset[Deps]):
    @property
    def id(self) -> str:
        return "rimbridge"

    async def get_tools(self, ctx: RunContext[Deps]) -> dict[str, ToolsetTool[Deps]]:
        return {
            m.tool_name: ToolsetTool(
                toolset=self,
                tool_def=ToolDefinition(name=m.tool_name, parameters_json_schema=m.schema, description=f"[RimBridge {m.name}] {m.doc}"[:1500],
                                        metadata={METHOD: m.name}, return_schema={}),
                max_retries=3,
                args_validator=ARGS_VALIDATOR,
            )
            for m in ctx.deps.catalog
        }

    async def call_tool(self, name: str, tool_args: dict[str, Any], ctx: RunContext[Deps], tool: ToolsetTool[Deps]) -> Any:
        method = bridge_method(tool.tool_def)
        assert method is not None, f"{name} is not a RimBridge tool"
        try:
            return await ctx.deps.bridge.call(method, bridge_params(tool_args))
        except BridgeError as e:
            raise ToolFailed(str(e)) from e
