"""Undo JSON that the model put inside string arguments ("[97, 98]", "true"), unless the tool schema asks for a string."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability, RawToolArgs
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import ToolDefinition

_JSON_SCALAR = re.compile(r"^(true|false|null|-?\d+(\.\d+)?)$")


def coerce(value: Any) -> Any:
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


def _decode(args: str) -> Any:
    value: Any = args
    while isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def _wants_string(schema: Any) -> bool:
    if not isinstance(schema, dict):
        return False
    kind = schema.get("type")
    if kind == "string" or (isinstance(kind, list) and "string" in kind):
        return True
    return any(_wants_string(s) for s in [*schema.get("anyOf", []), *schema.get("oneOf", [])])


@dataclass
class CoerceArguments(AbstractCapability[Any]):
    async def before_tool_validate(self, ctx: RunContext[Any], *, call: ToolCallPart, tool_def: ToolDefinition, args: RawToolArgs) -> RawToolArgs:
        decoded = _decode(args) if isinstance(args, str) else args
        if not isinstance(decoded, dict):
            return args
        properties = tool_def.parameters_json_schema.get("properties", {})
        return {k: v if _wants_string(properties.get(k)) else coerce(v) for k, v in decoded.items()}
