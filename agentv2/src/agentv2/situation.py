"""The situation report: the user prompt of every think step. What woke the director and what needs an answer first,
then what changed since its last step and what is wrong, then the colony."""
from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .bridge import Bridge, BridgeError
from .watchers import Alert
from .world import Tracked, View, changes, show

STATUS_NUMBERS = ("wealth", "food_days", "mood_avg", "threat_points", "research_done")
MAX_EVENTS = 60
MAX_ROOMS = 14
MAX_HOSTILES = 15
MAX_MEMORY_CHARS = 6000


@dataclass(frozen=True)
class Snapshot:
    """What the game says now."""

    summary: dict[str, Any]
    base: dict[str, Any] = field(default_factory=dict)
    dialogs: Any = None
    letters: Any = None
    threats: Any = None
    errors: list[str] = field(default_factory=list)

    @property
    def numbers(self) -> dict[str, float]:
        return {k: float(self.summary[k]) for k in STATUS_NUMBERS if isinstance(self.summary.get(k), (int, float))}

    @property
    def view(self) -> View:
        return View.of(self.summary, self.base)


@dataclass(frozen=True)
class Wakeup:
    """What the runner knows about this step. `previous` is what the director saw at its last step."""

    trigger: str
    events: list[dict[str, Any]] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    operator: list[str] = field(default_factory=list)
    previous: View | None = None
    tracked: dict[str, Tracked] = field(default_factory=dict)
    problems: dict[str, str] = field(default_factory=dict)
    sandbox: bool = False
    show_base: bool = True
    notebook: str | None = None
    journal: str | None = None
    loop: str | None = None


@dataclass
class Report:
    text: str
    numbers: dict[str, float]
    changes: str
    day: int | None
    hour: int | None


async def read(bridge: Bridge) -> Snapshot:
    (summary, error), (base, base_error), (dialogs, _), (letters, _) = await asyncio.gather(
        _read(bridge, "state.summary"), _read(bridge, "state.base"), _read(bridge, "state.dialogs"), _read(bridge, "state.letters"))
    summary = summary if isinstance(summary, dict) else {}
    threats = (await _read(bridge, "state.threats"))[0] if summary.get("hostiles") else None
    return Snapshot(summary, base if isinstance(base, dict) else {}, dialogs, letters, threats, [e for e in (error, base_error) if e])


def render(snap: Snapshot, wake: Wakeup) -> Report:
    parts = [text for section in SECTIONS if (text := section(snap, wake))]
    parts.append("Act now. Finish with end_turn (notes and a wake plan).")
    brief = ", ".join(_brief(label, t) for label, t in wake.tracked.items() if t.history)
    return Report("\n\n".join(parts), snap.numbers, brief, snap.summary.get("day"), snap.summary.get("hour"))


def wake_text(snap: Snapshot, wake: Wakeup) -> str:
    """What woke the director: the trigger, the new events, the watcher alerts and the game alerts."""
    return "\n".join([wake.trigger, *(f"{e.get('kind')}: {e.get('text', '')}" for e in wake.events), *(a.text for a in wake.alerts),
                      *(str(a.get("label")) for a in snap.summary.get("alerts") or [] if isinstance(a, dict))])


async def _read(bridge: Bridge, method: str) -> tuple[Any, str | None]:
    try:
        return await bridge.call(method), None
    except BridgeError as e:
        return None, f"{method} unavailable: {e}"


def _brief(label: str, tracked: Tracked) -> str:
    now = tracked.history[-1]
    before = tracked.history[-2] if len(tracked.history) > 1 else None
    if isinstance(now, float) and isinstance(before, float):
        return f"{label} {now:g} ({'+' if now > before else ''}{now - before:.4g})"
    return f"{label} {show(now)}"


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
    temp = f", {s['temp_outdoor']}C" if s.get("temp_outdoor") is not None else ""
    head = f"day {s.get('day')} {s.get('hour')}h, {s.get('season', '')}, {s.get('weather', '')}{temp}; colonists {s.get('colonists')}"
    if s.get("downed"):
        head += f" ({s['downed']} downed)"
    if s.get("danger") not in (None, "None"):
        head += f"; danger {s['danger']}"
    return "## Now\n" + "\n".join([head, *snap.errors])


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
    return "## Alerts from watchers and the fast loop\n" + "\n".join(f"- {a.watcher}: {a.text}" for a in wake.alerts)


def _loop(snap: Snapshot, wake: Wakeup) -> str | None:
    if not wake.loop:
        return None
    return "## Fast loop (Jev policies) since your last step\n" + wake.loop


def _threats(snap: Snapshot, wake: Wakeup) -> str | None:
    hostiles = snap.threats.get("hostiles") if isinstance(snap.threats, dict) else snap.summary.get("hostiles")
    hostiles = [h for h in hostiles or [] if isinstance(h, dict)]
    if not hostiles:
        return None
    lines = [_hostile(h) for h in hostiles[:MAX_HOSTILES]]
    if len(hostiles) > MAX_HOSTILES:
        lines.append(f"- ... {len(hostiles) - MAX_HOSTILES} more (rw_state_threats)")
    points = snap.threats.get("threat_points") if isinstance(snap.threats, dict) else snap.summary.get("threat_points")
    return f"## THREATS: {len(hostiles)} hostile (threat points {points})\n" + "\n".join(lines)


def _hostile(h: dict[str, Any]) -> str:
    who = h.get("name") or h.get("label") or h.get("def") or h.get("id")
    bits = [f"{h['faction']}" if h.get("faction") else "", f"weapon {h['weapon']}" if h.get("weapon") else "",
            f"{h['dist_home']} cells from home" if h.get("dist_home") is not None else f"at {h.get('pos')}",
            f"health {h['health']}" if h.get("health") is not None else "", str(h.get("mental") or ""), str(h.get("lord") or "")]
    return f"- {who}: " + ", ".join(b for b in bits if b)


def _game_alerts(snap: Snapshot, wake: Wakeup) -> str | None:
    alerts = [a for a in snap.summary.get("alerts") or [] if isinstance(a, dict)][:12]
    if not alerts:
        return None
    return "## Game alerts\n" + "\n".join(f"- [{a.get('priority')}] {a.get('label')}: {str(a.get('explanation', ''))[:160]}" for a in alerts)


def _changes(snap: Snapshot, wake: Wakeup) -> str | None:
    if wake.previous is None or not snap.summary:
        return None
    lines = changes(wake.previous, snap.view)
    since = f"day {wake.previous.day} {wake.previous.hour}h"
    return f"## Since your last step ({since})\n" + ("\n".join(f"- {line}" for line in lines) or "- nothing notable changed")


def _tracked(snap: Snapshot, wake: Wakeup) -> str | None:
    if not wake.tracked:
        return None
    return ("## Tracked values (oldest -> newest; change them with track_value / untrack_value)\n"
            + "\n".join(t.line(label) for label, t in wake.tracked.items()))


def _problems(snap: Snapshot, wake: Wakeup) -> str | None:
    base, outside = snap.base, snap.summary.get("outside_storage") or {}
    lines = [f"- {r.get('ref')} {r.get('role')}: {', '.join(map(str, r['problems']))}"
             for r in base.get("rooms") or [] if isinstance(r, dict) and r.get("problems")][:10]
    lines += [f"- TRAPPED: {t.get('pawn')} at {t.get('at')}: {t.get('note', '')}" for t in base.get("trapped_colonists") or [] if isinstance(t, dict)]
    if furniture := base.get("furniture_not_in_any_room"):
        lines.append(f"- furniture outside any room (open to the sky or walls missing): {furniture}")
    if bad := {k: outside[k] for k in ("rotting", "unroofed_deteriorating", "corpses", "forbidden") if isinstance(outside, dict) and outside.get(k)}:
        lines.append("- outside storage: " + ", ".join(f"{k} {v}" for k, v in bad.items()) + f" (free storage cells {outside.get('storage_cells_free')})")
    return "## Problems\n" + "\n".join(lines) if lines else None


def _colonists(snap: Snapshot, wake: Wakeup) -> str | None:
    colonists = [c for c in snap.summary.get("colonist_list") or [] if isinstance(c, dict)]
    if not colonists:
        return None
    return "## Colonists\n" + "\n".join(_colonist(c) for c in colonists)


def _colonist(c: dict[str, Any]) -> str:
    flags = " DOWNED" if c.get("downed") or c.get("job") == "downed" else ""
    flags += f" MENTAL: {c['mental_state']}" if c.get("mental_state") else ""
    flags += f" bleeding {c['bleeding']}" if c.get("bleeding") else ""
    flags += " needs tending" if c.get("needs_tending") else ""
    skills = f"; {c['top_skills']}" if c.get("top_skills") else ""
    return (f"- {c.get('name')} ({c.get('id')}) at {c.get('pos')}: mood {c.get('mood')}, health {c.get('health')}, {c.get('job')}{skills}; "
            f"weapon {c.get('weapon') or 'none'}{flags}")


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


def _base(snap: Snapshot, wake: Wakeup) -> str | None:
    if not wake.show_base or not snap.base:
        return None
    base = snap.base
    rooms = [r for r in base.get("rooms") or [] if isinstance(r, dict)]
    lines = [_room(r) for r in rooms[:MAX_ROOMS]] or ["- no enclosed rooms yet"]
    if len(rooms) > MAX_ROOMS:
        lines.append(f"- ... {len(rooms) - MAX_ROOMS} more rooms (rw_state_base)")
    if outside := base.get("structures_outside_rooms"):
        lines.append("- outside rooms: " + ", ".join(f"{k} x{len(v) if isinstance(v, list) else str(v).split(' ')[0]}" for k, v in list(outside.items())[:12]))
    anchors = [a for a in base.get("anchors") or [] if isinstance(a, dict)]
    lines.append("- anchors: " + (", ".join(f"{a.get('name')} ({a.get('size')}, {a.get('from_home')})" for a in anchors[:16])
                                  or "none yet; name rooms and sites with rw_anchor_set"))
    lines.append(f"- blueprints pending {base.get('blueprints_pending')}, frames in progress {base.get('frames_in_progress')}")
    stocks = snap.summary.get("key_stocks")
    if stocks:
        lines.append(f"- key stocks (stored): {json.dumps(stocks, ensure_ascii=False)[:1500]}")
    return "## The base (later reports show only what changed; rw_state_base reads it all)\n" + "\n".join(lines)


def _room(r: dict[str, Any]) -> str:
    doors = r.get("doors") or []
    leads = ", ".join(str(d.get("leads_to")) for d in doors if isinstance(d, dict)) or "none"
    contents = ", ".join(f"{k} x{v if isinstance(v, int) else len(v)}" for k, v in (r.get("contents") or {}).items())
    line = f"- {r.get('ref')} {r.get('role')} {r.get('size')}, free floor {r.get('free_floor')}, doors to {leads}, {r.get('temp')}C [{contents}]"
    return line + (f" owners {r['owners']}" if r.get("owners") else "")


def _notebook(snap: Snapshot, wake: Wakeup) -> str | None:
    if wake.notebook is None:
        return None
    return "## Your colony notebook (as it is now; notebook_* tools change it)\n" + (_tail(wake.notebook, MAX_MEMORY_CHARS) or "(empty)")


def _journal(snap: Snapshot, wake: Wakeup) -> str | None:
    if not wake.journal:
        return None
    return "## Journal: lessons from earlier games (the latest part; journal_* tools read and change it)\n" + _tail(wake.journal, MAX_MEMORY_CHARS)


def _tail(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else "..." + text[-limit:]


def _brain_problems(snap: Snapshot, wake: Wakeup) -> str | None:
    if not wake.problems:
        return None
    return "## Brain problems (fix them)\n" + "\n".join(f"- {k}: {_last_line(v)}" for k, v in wake.problems.items())


def _last_line(text: str) -> str:
    lines = text.strip().splitlines()
    return lines[-1][:300] if lines else text


SECTIONS: list[Callable[[Snapshot, Wakeup], str | None]] = [
    _trigger, _operator, _sandbox, _now, _dialogs, _letters, _events, _watcher_alerts, _loop, _threats, _game_alerts, _changes, _tracked,
    _problems, _colonists, _steward, _base, _journal, _notebook, _brain_problems,
]
