"""The bridge method catalog (GET /methods) as tool definitions.

RimBridge docs open with a parameter sketch, e.g. `{pawn, cell: [x,z], draft?: true} move a pawn`. It becomes a JSON
schema with the parameter names, the types that are clear from the sketch, and `additionalProperties: true`, so the
model sees named, typed arguments and the server can convert them, while an unexpected argument still goes through.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

HIDDEN = {"bridge.methods", "map.screenshot_bytes", "game.new_game", "game.load", "game.quit_to_menu", "game.dev_mode"}
READ_PREFIXES = ("state.", "map.", "defs.", "anchor.list", "game.status", "game.list_saves", "game.log_tail",
                 "engine.get", "engine.members", "engine.types", "steward.status", "steward.explain", "steward.stock.list",
                 "steward.orders", "steward.orders.explain")
_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")
_GROUP_ALTERNATIVE = re.compile(r"\s\|\s(?=[a-z_]+\?)")
_NUMBER = re.compile(r"^(int|float|number|n|-?\d+(\.\d+)?(\.\.-?\d+(\.\d+)?)?|-?\d+(\.\d+)?\s*-\s*-?\d+(\.\d+)?)\b")


@dataclass(frozen=True)
class Method:
    name: str
    doc: str
    schema: dict[str, Any]

    @property
    def tool_name(self) -> str:
        return self.name.replace(".", "_")

    @property
    def group(self) -> str:
        return self.name.split(".", 1)[0]

    @property
    def read_only(self) -> bool:
        return is_read_only(self.name)

    @property
    def dev(self) -> bool:
        return self.group == "dev"


def is_read_only(method: str) -> bool:
    return any(method == p or (p.endswith(".") and method.startswith(p)) for p in READ_PREFIXES)


def _split_top(text: str, sep: str = ",") -> list[str]:
    parts, depth, cur = [], 0, []
    for ch in text:
        if ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def _sketch(doc: str) -> str | None:
    doc = doc.lstrip()
    if not doc.startswith("{"):
        return None
    depth = 0
    for i, ch in enumerate(doc):
        depth += ch in "{[("
        depth -= ch in "}])"
        if depth == 0:
            return doc[1:i]
    return None


def _type_of(hint: str) -> dict[str, Any]:
    h = hint.strip()
    first = _split_top(h, "|")[0] if h else ""
    if len(_split_top(h, "|")) > 1 and any(p.strip().startswith(("[", "{")) for p in _split_top(h, "|")):
        return {}
    word = first.split()[0].rstrip(",;") if first else ""
    if word in ("bool", "true", "false") or word.startswith("bool"):
        return {"type": "boolean"}
    if first.startswith("[") or first.startswith("list"):
        return {"type": "array"}
    if first.startswith("{"):
        return {"type": "object"}
    if _NUMBER.match(first):
        return {"type": "integer"} if first.startswith("int") else {"type": "number"}
    return {}


def parse_schema(doc: str) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": True}
    sketch = _sketch(doc)
    if not sketch:
        return schema
    required: list[str] = []
    entries = [part for entry in _split_top(sketch) for part in _GROUP_ALTERNATIVE.split(entry)]
    for entry in entries:
        key, _, hint = entry.partition(":")
        names = [n.strip() for n in re.split(r"[/|]", key) if n.strip()]
        alternatives = len(names) > 1
        for raw in names:
            optional = raw.endswith("?") or alternatives
            name = raw.rstrip("?")
            if not _NAME.match(name):
                continue
            prop = _type_of(hint) if hint else {}
            if hint.strip():
                prop["description"] = hint.strip()
            schema["properties"].setdefault(name, prop)
            if not optional and name not in required:
                required.append(name)
    if required:
        schema["required"] = required
    return schema


def parse_catalog(methods: list[dict[str, str]]) -> list[Method]:
    out = []
    for m in methods:
        name, doc = m.get("method", ""), m.get("doc", "")
        if not name or name in HIDDEN:
            continue
        out.append(Method(name=name, doc=doc, schema=parse_schema(doc)))
    return out
