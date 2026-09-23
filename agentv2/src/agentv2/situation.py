"""The situation report: the user prompt of every think step. Change first, then what needs an answer, then the colony."""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .bridge import Bridge, BridgeError
from .watchers import Alert

TRACKED = ("wealth", "food_days", "mood_avg", "threat_points", "research_done")
MAX_EVENTS = 60


@dataclass(frozen=True)
class Snapshot:
    """What the game says now."""

    summary: dict[str, Any]
    dialogs: Any = None
    letters: Any = None
    error: str | None = None

    @property
    def numbers(self) -> dict[str, float]:
        return {k: float(self.summary[k]) for k in TRACKED if isinstance(self.summary.get(k), (int, float))}


@dataclass(frozen=True)
class Wakeup:
    """What the runner knows about this step."""

    trigger: str
    events: list[dict[str, Any]] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    operator: list[str] = field(default_factory=list)
    previous: dict[str, float] = field(default_factory=dict)
    problems: dict[str, str] = field(default_factory=dict)
    sandbox: bool = False


@dataclass
class Report:
    text: str
    numbers: dict[str, float]
    changes: str
    day: int | None
    hour: int | None


async def read(bridge: Bridge) -> Snapshot:
    summary, error = await _read(bridge, "state.summary")
    dialogs, _ = await _read(bridge, "state.dialogs")
    letters, _ = await _read(bridge, "state.letters")
    return Snapshot(summary if isinstance(summary, dict) else {}, dialogs, letters, error)


def render(snap: Snapshot, wake: Wakeup) -> Report:
    parts = [text for section in SECTIONS if (text := section(snap, wake))]
    parts.append("Act now. Finish with end_turn (notes and a wake plan).")
    return Report("\n\n".join(parts), snap.numbers, _changes(snap, wake), snap.summary.get("day"), snap.summary.get("hour"))


async def _read(bridge: Bridge, method: str) -> tuple[Any, str | None]:
    try:
        return await bridge.call(method), None
    except BridgeError as e:
        return None, f"{method} unavailable: {e}"


def _changes(snap: Snapshot, wake: Wakeup) -> str:
    return ", ".join(_delta(k, v, wake.previous.get(k)) for k, v in snap.numbers.items())


def _delta(name: str, now: float, before: float | None) -> str:
    if before is None or abs(now - before) < 1e-9:
        return f"{name} {now:g}"
    return f"{name} {now:g} ({'+' if now > before else ''}{now - before:.4g})"


def _trigger(snap: Snapshot, wake: Wakeup) -> str:
    return f"## Wake trigger\n{wake.trigger}"


def _operator(snap: Snapshot, wake: Wakeup) -> str | None:
    if not wake.operator:
        return None
    return ("## Message from the human operator\nAnswer it FIRST with reply_to_operator. If it is advice on how to play, "
            "write it into the relevant skill (mark the line 'operator tip').\n" + "\n".join(f"- {m}" for m in wake.operator))


def _sandbox(snap: Snapshot, wake: Wakeup) -> str | None:
    if not wake.sandbox:
        return None
    return ("## SANDBOX EPISODE (not scored)\nGod mode is on and research is unlocked. Experiment: try layouts, power, defenses "
            "(rw_dev_incident), then write what you learned into skills with numbers.")


def _now(snap: Snapshot, wake: Wakeup) -> str:
    s = snap.summary
    head = f"day {s.get('day')} {s.get('hour')}h, {s.get('season', '')}, colonists {s.get('colonists')}"
    return f"## Now\n{head}\n{_changes(snap, wake) or snap.error or 'no numbers'}"


def _dialogs(snap: Snapshot, wake: Wakeup) -> str | None:
    if not snap.dialogs:
        return None
    return "## OPEN DIALOGS: the game waits until you answer with rw_ui_dialog\n" + json.dumps(snap.dialogs, ensure_ascii=False)[:5000]


def _letters(snap: Snapshot, wake: Wakeup) -> str | None:
    if not snap.letters:
        return None
    return "## Letters waiting (answer with rw_ui_letter)\n" + json.dumps(snap.letters, ensure_ascii=False)[:4000]


def _events(snap: Snapshot, wake: Wakeup) -> str | None:
    if not wake.events:
        return None
    lines = [f"- [{e.get('day', '?')}d {e.get('hour', '?')}h] {e.get('kind')}: {e.get('text', '')}" for e in wake.events[-MAX_EVENTS:]]
    more = f" (showing the last {MAX_EVENTS})" if len(wake.events) > MAX_EVENTS else ""
    return f"## New events since your last step: {len(wake.events)}{more}\n" + "\n".join(lines)


def _watcher_alerts(snap: Snapshot, wake: Wakeup) -> str | None:
    if not wake.alerts:
        return None
    return "## Watcher alerts\n" + "\n".join(f"- {a.watcher}: {a.text}" for a in wake.alerts)


def _game_alerts(snap: Snapshot, wake: Wakeup) -> str | None:
    alerts = [a for a in snap.summary.get("alerts") or [] if isinstance(a, dict)][:12]
    if not alerts:
        return None
    return "## Game alerts\n" + "\n".join(f"- [{a.get('priority')}] {a.get('label')}: {str(a.get('explanation', ''))[:160]}" for a in alerts)


def _colonists(snap: Snapshot, wake: Wakeup) -> str | None:
    colonists = [c for c in snap.summary.get("colonist_list") or [] if isinstance(c, dict)]
    if not colonists:
        return None
    return "## Colonists\n" + "\n".join(_colonist(c) for c in colonists)


def _colonist(c: dict[str, Any]) -> str:
    flags = " DOWNED" if c.get("downed") else ""
    flags += f" MENTAL: {c['mental_state']}" if c.get("mental_state") else ""
    return f"- {c.get('name')} ({c.get('id')}) at {c.get('pos')}: mood {c.get('mood')}, health {c.get('health')}, {c.get('job')}{flags}"


def _steward(snap: Snapshot, wake: Wakeup) -> str | None:
    block = snap.summary.get("steward")
    if not isinstance(block, dict):
        return None
    posture = block.get("posture")
    lines = [f"posture: {posture.get('label', '?') if isinstance(posture, dict) else posture or 'none'}"]
    lines += [f"- problem: {p}" for p in (block.get("problems") or [])[:5]]
    if block.get("stock_brief"):
        lines.append(f"stock: {json.dumps(block['stock_brief'], ensure_ascii=False)[:600]}")
    if block.get("orders_active"):
        lines.append(f"standing orders acting: {', '.join(map(str, block['orders_active']))}")
    if block.get("rally") is False:
        lines.append("rally: none (set one with rw_steward_orders_rally so the combat order has somewhere to hold)")
    return "## Steward (sets work priorities, keeps stock targets, runs the standing orders; you direct it)\n" + "\n".join(lines)


def _stocks(snap: Snapshot, wake: Wakeup) -> str | None:
    stocks = snap.summary.get("key_stocks")
    return f"## Key stocks\n{json.dumps(stocks, ensure_ascii=False)[:1500]}" if stocks else None


def _problems(snap: Snapshot, wake: Wakeup) -> str | None:
    if not wake.problems:
        return None
    return "## Brain problems (fix them)\n" + "\n".join(f"- {k}: {_last_line(v)}" for k, v in wake.problems.items())


def _last_line(text: str) -> str:
    lines = text.strip().splitlines()
    return lines[-1][:300] if lines else text


SECTIONS: list[Callable[[Snapshot, Wakeup], str | None]] = [
    _trigger, _operator, _sandbox, _now, _dialogs, _letters, _events, _watcher_alerts, _game_alerts, _colonists, _steward, _stocks, _problems,
]
