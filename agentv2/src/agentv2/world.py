"""What the director saw at its last step, what changed since, and the values it tracks. Kept in the episode."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from pydantic import BaseModel, Field

from .bridge import Bridge, BridgeError

SUMMARY = "state.summary"
HISTORY = 8


class RoomView(BaseModel):
    role: str | None = None
    size: str | None = None
    problems: list[str] = Field(default_factory=list)
    contents: dict[str, int] = Field(default_factory=dict)


class ColonistView(BaseModel):
    mood: float | None = None
    health: float | None = None
    state: str = ""


class View(BaseModel):
    day: int | None = None
    hour: int | None = None
    research: str | None = None
    stocks: dict[str, float] = Field(default_factory=dict)
    rooms: dict[str, RoomView] = Field(default_factory=dict)
    colonists: dict[str, ColonistView] = Field(default_factory=dict)
    trapped: list[str] = Field(default_factory=list)
    furniture_out: str | None = None
    blueprints: int = 0
    frames: int = 0

    @classmethod
    def of(cls, summary: dict[str, Any], base: dict[str, Any]) -> View:
        return cls(
            day=summary.get("day"),
            hour=summary.get("hour"),
            research=summary.get("research_current"),
            stocks={k: float(v) for k, v in (summary.get("key_stocks") or {}).items() if isinstance(v, int | float)},
            rooms={str(r.get("ref")): RoomView(role=r.get("role"), size=r.get("size"), problems=list(r.get("problems") or []), contents=_counts(r.get("contents")))
                   for r in base.get("rooms") or [] if isinstance(r, dict)},
            colonists={str(c.get("name")): ColonistView(mood=c.get("mood"), health=c.get("health"), state=_state(c))
                       for c in summary.get("colonist_list") or [] if isinstance(c, dict)},
            trapped=[str(t.get("pawn")) for t in base.get("trapped_colonists") or [] if isinstance(t, dict)],
            furniture_out=base.get("furniture_not_in_any_room"),
            blueprints=int(base.get("blueprints_pending") or summary.get("blueprints") or 0),
            frames=int(base.get("frames_in_progress") or summary.get("frames") or 0),
        )


def _counts(contents: Any) -> dict[str, int]:
    if not isinstance(contents, dict):
        return {}
    return {k: v if isinstance(v, int) else len(v) for k, v in contents.items() if isinstance(v, int | list)}


def _state(colonist: dict[str, Any]) -> str:
    return "downed" if colonist.get("downed") or colonist.get("job") == "downed" else str(colonist.get("mental_state") or "")


def changes(before: View, now: View, limit: int = 30) -> list[str]:
    out = [f"research: {before.research} -> {now.research}"] if before.research != now.research else []
    out += _colonist_changes(before, now) + _room_changes(before, now)
    if now.trapped:
        out.append("TRAPPED: " + ", ".join(now.trapped))
    if before.furniture_out != now.furniture_out:
        out.append(f"furniture outside rooms: {before.furniture_out or 'none'} -> {now.furniture_out or 'none'}")
    if (before.blueprints, before.frames) != (now.blueprints, now.frames):
        out.append(f"blueprints {before.blueprints} -> {now.blueprints}, frames {before.frames} -> {now.frames}")
    elif now.blueprints + now.frames:
        out.append(f"blueprints {now.blueprints} and frames {now.frames} did not change: is anybody building?")
    for name in sorted(set(before.stocks) | set(now.stocks)):
        a, b = before.stocks.get(name, 0.0), now.stocks.get(name, 0.0)
        if abs(b - a) >= max(1.0, 0.1 * abs(a)):
            out.append(f"{name} {a:g} -> {b:g}")
    return out[:limit] + ([f"... {len(out) - limit} more"] if len(out) > limit else [])


def _colonist_changes(before: View, now: View) -> list[str]:
    out = [f"colonist joined: {n}" for n in now.colonists if n not in before.colonists]
    out += [f"colonist gone: {n}" for n in before.colonists if n not in now.colonists]
    for name, c in now.colonists.items():
        if (p := before.colonists.get(name)) is None:
            continue
        if c.state != p.state:
            out.append(f"{name}: {p.state or 'ok'} -> {c.state or 'ok'}")
        if p.mood is not None and c.mood is not None and abs(c.mood - p.mood) >= 8:
            out.append(f"{name} mood {p.mood:g} -> {c.mood:g}")
        if p.health is not None and c.health is not None and abs(c.health - p.health) >= 10:
            out.append(f"{name} health {p.health:g} -> {c.health:g}")
    return out


def _room_changes(before: View, now: View) -> list[str]:
    out = [f"room {ref} gone (opened, merged or destroyed)" for ref in before.rooms if ref not in now.rooms]
    for ref, r in now.rooms.items():
        if (p := before.rooms.get(ref)) is None:
            out.append(f"NEW room {ref} {r.role} {r.size}" + (f"; problems: {', '.join(r.problems)}" if r.problems else ""))
            continue
        bits = [f"{k} {getattr(p, k)} -> {getattr(r, k)}" for k in ("role", "size") if getattr(p, k) != getattr(r, k)]
        bits += [f"{d} {p.contents.get(d, 0)} -> {r.contents.get(d, 0)}" for d in sorted(set(p.contents) | set(r.contents))
                 if p.contents.get(d, 0) != r.contents.get(d, 0)]
        if fixed := set(p.problems) - set(r.problems):
            bits.append("fixed: " + ", ".join(sorted(fixed)))
        if new := set(r.problems) - set(p.problems):
            bits.append("NEW PROBLEM: " + ", ".join(sorted(new)))
        if bits:
            out.append(f"{ref} {r.role}: " + "; ".join(bits))
    return out


Value = float | str | None


class Tracked(BaseModel):
    """A value the director tracks: `path` into the result of a read-only RimBridge method. A `#` segment counts a list."""

    path: str
    method: str = SUMMARY
    params: dict[str, Any] = Field(default_factory=dict)
    history: list[Value] = Field(default_factory=list)

    def record(self, value: Value) -> None:
        if not self.history or self.history[-1] != value:
            self.history = [*self.history, value][-HISTORY:]

    def line(self, label: str) -> str:
        shown = " -> ".join(show(v) for v in self.history[-5:]) or "(not read yet)"
        numbers = [v for v in self.history if isinstance(v, float)]
        arrow = "" if len(numbers) < 2 else " up" if numbers[-1] > numbers[-2] else " down" if numbers[-1] < numbers[-2] else ""
        return f"- {label}: {shown}{arrow}"


def default_tracked() -> dict[str, Tracked]:
    paths = {"food_days": "food_days", "mood_avg": "mood_avg", "colonists": "colonists", "wealth": "wealth", "threat_points": "threat_points",
             "research_done": "research_done", "wood": "key_stocks.WoodLog", "loose_stacks": "outside_storage.stacks"}
    return {label: Tracked(path=path) for label, path in paths.items()}


def dig(value: Any, path: str) -> Any:
    for part in [p for p in path.split(".") if p]:
        if part == "#":
            value = len(value) if isinstance(value, list | dict) else None
        elif isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.lstrip("-").isdigit() and -len(value) <= int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    return value


def as_value(value: Any) -> Value:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int | float):
        return round(float(value), 2)
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)[:60]


async def read_value(bridge: Bridge, tracked: Tracked, summary: dict[str, Any] | None = None) -> Value:
    source = summary if tracked.method == SUMMARY and summary is not None else await bridge.call(tracked.method, tracked.params)
    return as_value(dig(source, tracked.path))


async def sample(bridge: Bridge, tracked: dict[str, Tracked], summary: dict[str, Any]) -> None:
    """Read every tracked value once (one call per method and params) and add it to its history."""
    reads: dict[str, Any] = {}
    for t in tracked.values():
        key = json.dumps([t.method, t.params], sort_keys=True)
        if t.method != SUMMARY and key not in reads:
            reads[key] = _call(bridge, t.method, t.params)
    results = dict(zip(reads, await asyncio.gather(*reads.values()), strict=True))
    for t in tracked.values():
        source = summary if t.method == SUMMARY else results[json.dumps([t.method, t.params], sort_keys=True)]
        t.record(f"error: {source}"[:60] if isinstance(source, BridgeError) else as_value(dig(source, t.path)))


async def _call(bridge: Bridge, method: str, params: dict[str, Any]) -> Any:
    try:
        return await bridge.call(method, params)
    except BridgeError as e:
        return e


def show(value: Value) -> str:
    return "?" if value is None else f"{value:g}" if isinstance(value, float) else str(value)
