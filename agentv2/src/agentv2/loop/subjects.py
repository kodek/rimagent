"""What the fast loop decides about. A subject reads the game through the shared screen cache, turns each thing into an
entity (the part of the Jev state about it, and its options), and knows the one RimBridge method that acts on it.

Code computes, Jev judges: numbers reach Jev with a literal band ("4.5 days (low: under 5 days)") because it cannot
compare them itself."""
from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar

from ..bridge import Bridge
from ..config import LoopSettings

TEXT_CLIP = 1500
DIALOG_TYPES = frozenset({"Dialog_NodeTree", "Dialog_MessageBox"})
POSTURES = ("normal", "defend", "build", "harvest", "recover")


@dataclass(frozen=True)
class Entity:
    key: str
    summary: str
    state: dict[str, Any]
    options: tuple[str, ...] = ()
    target: dict[str, Any] = field(default_factory=dict)
    current: str | None = None


class Screen:
    """Short-lived reads of the game shared by all policies: one bridge call per method and maximum age."""

    def __init__(self, bridge: Bridge, clock: Callable[[], float] = time.monotonic) -> None:
        self.bridge = bridge
        self._clock = clock
        self._cache: dict[str, tuple[float, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def read(self, method: str, max_age: float) -> Any:
        async with self._locks.setdefault(method, asyncio.Lock()):
            cached = self._cache.get(method)
            if cached and self._clock() - cached[0] <= max_age:
                return cached[1]
            value = await self.bridge.call(method)
            self._cache[method] = (self._clock(), value)
            return value

    def forget(self, method: str) -> None:
        self._cache.pop(method, None)


class Subject:
    name: ClassVar[str]
    method: ClassVar[str | None] = None
    claimable: ClassVar[frozenset[str]] = frozenset()
    has_options: ClassVar[bool] = False
    reads: ClassVar[str | None] = None

    def accepts(self, event: dict[str, Any]) -> bool:
        return False

    def claim_key(self, event: dict[str, Any]) -> str | None:
        return None

    async def entities(self, screen: Screen, events: list[dict[str, Any]], settings: LoopSettings) -> list[Entity]:
        raise NotImplementedError

    def call(self, entity: Entity, label: str, params: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(f"{self.name} does not act")


class EventsSubject(Subject):
    name = "events"

    async def entities(self, screen: Screen, events: list[dict[str, Any]], settings: LoopSettings) -> list[Entity]:
        return [Entity(key=f"event:{e.get('seq')}", summary=f"{e.get('kind')}: {str(e.get('text', ''))[:100]}",
                       state={"event": {k: _clip(e[k]) for k in ("kind", "text", "day", "hour", "data") if k in e}}) for e in events]


class LettersSubject(Subject):
    name = "letters"
    method = "ui.letter"
    claimable = frozenset({"letter"})
    has_options = True
    reads = "state.letters"

    def accepts(self, event: dict[str, Any]) -> bool:
        return event.get("kind") == "letter" and isinstance(event.get("data"), dict) and "id" in event["data"]

    def claim_key(self, event: dict[str, Any]) -> str | None:
        return f"letter:{event['data']['id']}" if self.accepts(event) else None

    async def entities(self, screen: Screen, events: list[dict[str, Any]], settings: LoopSettings) -> list[Entity]:
        letters = await screen.read("state.letters", settings.screen_max_age_s) or []
        return [Entity(key=f"letter:{x['id']}", summary=f"letter \"{x.get('label')}\"",
                       state={"letter": {"label": x.get("label"), "text": _clip(x.get("text", "")), "choices": list(_unique(x["choices"]))}},
                       options=_unique(x["choices"]), target={"id": x["id"]})
                for x in letters if isinstance(x, dict) and x.get("choices")]

    def call(self, entity: Entity, label: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"id": entity.target["id"], "action": "choose", "choice": label}


class DialogsSubject(Subject):
    name = "dialogs"
    method = "ui.dialog"
    claimable = frozenset({"dialog"})
    has_options = True
    reads = "state.dialogs"

    def accepts(self, event: dict[str, Any]) -> bool:
        data = event.get("data")
        return event.get("kind") == "dialog" and isinstance(data, dict) and data.get("type") in DIALOG_TYPES and bool(_labels(data))

    def claim_key(self, event: dict[str, Any]) -> str | None:
        return _dialog_key(event["data"]) if self.accepts(event) else None

    async def entities(self, screen: Screen, events: list[dict[str, Any]], settings: LoopSettings) -> list[Entity]:
        dialogs = await screen.read("state.dialogs", settings.screen_max_age_s) or []
        return [Entity(key=_dialog_key(d), summary=f"dialog \"{str(d.get('title') or d.get('text', ''))[:80]}\"",
                       state={"dialog": {k: v for k, v in (("title", d.get("title")), ("text", _clip(d.get("text", ""))),
                                                           ("choices", list(_labels(d)))) if v}},
                       options=_labels(d), target={"i": d.get("i")})
                for d in dialogs if isinstance(d, dict) and d.get("type") in DIALOG_TYPES and _labels(d)]

    def call(self, entity: Entity, label: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"i": entity.target["i"], "choice": label}


class PostureSubject(Subject):
    name = "posture"
    method = "steward.posture"
    has_options = True
    reads = "state.summary"

    async def entities(self, screen: Screen, events: list[dict[str, Any]], settings: LoopSettings) -> list[Entity]:
        block = (await screen.read("state.summary", settings.summary_max_age_s) or {}).get("steward")
        if not isinstance(block, dict):
            return []
        current = str(block.get("posture") or "normal")
        return [Entity(key="colony", summary="Steward posture", state={"posture": {"current": current}}, options=POSTURES, current=current)]

    def call(self, entity: Entity, label: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"preset": label, "hours": float(params.get("hours", 12))}


SUBJECTS: dict[str, Subject] = {s.name: s for s in (EventsSubject(), LettersSubject(), DialogsSubject(), PostureSubject())}


# ---------------------------------------------------------------- colony features

def _band(value: Any, bands: list[tuple[float, str]], last: str) -> str:
    if not isinstance(value, (int, float)):
        return "unknown"
    return next((f"{value:g} ({label})" for limit, label in bands if value < limit), f"{value:g} ({last})")


def _alerts(s: dict[str, Any]) -> list[str]:
    return [str(a.get("label")) for a in s.get("alerts") or [] if isinstance(a, dict) and a.get("priority") in ("Critical", "High")][:5]


FEATURES: dict[str, Callable[[dict[str, Any]], Any]] = {
    "time": lambda s: f"day {s.get('day')} {s.get('hour')}h, {s.get('season', '')}, outdoor {s.get('temp_outdoor', '?')} C",
    "colonists": lambda s: {"count": s.get("colonists"), "downed": s.get("downed") or 0},
    "food": lambda s: _band(s.get("food_days"), [(2, "critical: under 2 days"), (5, "low: under 5 days"), (10, "enough: 5 to 10 days")],
                            "plenty: 10 days or more"),
    "mood": lambda s: _band(s.get("mood_avg"), [(35, "mental breaks likely"), (50, "low"), (70, "content")], "high"),
    "danger": lambda s: str(s.get("danger") or "None"),
    "hostiles": lambda s: len(s.get("hostiles") or []),
    "wealth": lambda s: s.get("wealth"),
    "research": lambda s: s.get("research_done"),
    "steward": lambda s: (s.get("steward") or {}).get("problems") or [] if isinstance(s.get("steward"), dict) else "not loaded",
    "alerts": _alerts,
}
DEFAULT_FEATURES = ["time", "colonists", "food", "mood", "danger", "hostiles"]


def colony_features(summary: dict[str, Any], names: list[str]) -> dict[str, Any]:
    return {name: FEATURES[name](summary) for name in names}


def _clip(value: Any) -> Any:
    return value[:TEXT_CLIP] + "…" if isinstance(value, str) and len(value) > TEXT_CLIP else value


def _unique(labels: list[Any]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(x) for x in labels))


def _labels(dialog: dict[str, Any]) -> tuple[str, ...]:
    return _unique([c.get("label") for c in dialog.get("choices") or [] if isinstance(c, dict) and not c.get("disabled")])


def _dialog_key(dialog: dict[str, Any]) -> str:
    text = "\n".join([str(dialog.get("type")), str(dialog.get("text", "")), *_labels(dialog)])
    return "dialog:" + hashlib.blake2b(text.encode(), digest_size=6).hexdigest()
