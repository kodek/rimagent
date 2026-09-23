"""The situation report: the user prompt of every think step. Change first, then what needs an answer, then the colony."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .bridge import Bridge, BridgeError

TRACKED = ("wealth", "food_days", "mood_avg", "threat_points", "research_done")
MAX_EVENTS = 60


@dataclass
class Report:
    text: str
    numbers: dict[str, float] = field(default_factory=dict)
    changes: str = ""
    day: int | None = None
    hour: int | None = None


async def _read(bridge: Bridge, method: str, params: dict[str, Any] | None = None) -> tuple[Any, str | None]:
    try:
        return await bridge.call(method, params or {}), None
    except BridgeError as e:
        return None, f"{method} unavailable: {e}"


def _delta(name: str, now: float, before: float | None) -> str:
    if before is None or abs(now - before) < 1e-9:
        return f"{name} {now:g}"
    return f"{name} {now:g} ({'+' if now > before else ''}{now - before:.4g})"


def _last_line(text: str) -> str:
    lines = text.strip().splitlines()
    return lines[-1][:300] if lines else text


def _colonist(c: dict[str, Any]) -> str:
    flags = " DOWNED" if c.get("downed") else ""
    flags += f" MENTAL: {c['mental_state']}" if c.get("mental_state") else ""
    return f"- {c.get('name')} ({c.get('id')}) at {c.get('pos')}: mood {c.get('mood')}, health {c.get('health')}, {c.get('job')}{flags}"


def _steward(block: Any) -> list[str]:
    if not isinstance(block, dict):
        return []
    posture = block.get("posture")
    lines = [f"posture: {posture.get('label', '?') if isinstance(posture, dict) else posture or 'none'}"]
    lines += [f"- problem: {p}" for p in (block.get("problems") or [])[:5]]
    if block.get("stock_brief"):
        lines.append(f"stock: {json.dumps(block['stock_brief'], ensure_ascii=False)[:600]}")
    if block.get("orders_active"):
        lines.append(f"standing orders acting: {', '.join(map(str, block['orders_active']))}")
    if block.get("rally") is False:
        lines.append("rally: none (set one with rw_steward_orders_rally so the combat order has somewhere to hold)")
    return lines


async def build(
    bridge: Bridge,
    trigger: str,
    events: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    operator: list[str],
    previous: dict[str, float],
    brain_errors: dict[str, str],
    sandbox: bool = False,
) -> Report:
    parts = [f"## Wake trigger\n{trigger}"]
    if operator:
        parts.append("## Message from the human operator\nAnswer it FIRST with reply_to_operator. If it is advice on how to play, "
                     "write it into the relevant skill (mark the line 'operator tip').\n" + "\n".join(f"- {m}" for m in operator))
    if sandbox:
        parts.append("## SANDBOX EPISODE (not scored)\nGod mode is on and research is unlocked. Experiment: try layouts, power, defenses "
                     "(rw_dev_incident), then write what you learned into skills with numbers.")
    summary, err = await _read(bridge, "state.summary")
    summary = summary if isinstance(summary, dict) else {}
    numbers = {k: float(summary[k]) for k in TRACKED if isinstance(summary.get(k), (int, float))}
    changes = ", ".join(_delta(k, v, previous.get(k)) for k, v in numbers.items())
    head = f"day {summary.get('day')} {summary.get('hour')}h, {summary.get('season', '')}, colonists {summary.get('colonists')}"
    parts.append(f"## Now\n{head}\n{changes or err or 'no numbers'}")
    dialogs, _ = await _read(bridge, "state.dialogs")
    if dialogs:
        parts.append("## OPEN DIALOGS: the game waits until you answer with rw_ui_dialog\n" + json.dumps(dialogs, ensure_ascii=False)[:5000])
    letters, _ = await _read(bridge, "state.letters")
    if letters:
        parts.append("## Letters waiting (answer with rw_ui_letter)\n" + json.dumps(letters, ensure_ascii=False)[:4000])
    if events:
        lines = [f"- [{e.get('day', '?')}d {e.get('hour', '?')}h] {e.get('kind')}: {e.get('text', '')}" for e in events[-MAX_EVENTS:]]
        more = f" (showing the last {MAX_EVENTS})" if len(events) > MAX_EVENTS else ""
        parts.append(f"## New events since your last step: {len(events)}{more}\n" + "\n".join(lines))
    if alerts:
        parts.append("## Watcher alerts\n" + "\n".join(f"- {a.get('watcher')}: {a.get('text')}" for a in alerts))
    if summary.get("alerts"):
        parts.append("## Game alerts\n" + "\n".join(f"- [{a.get('priority')}] {a.get('label')}: {str(a.get('explanation', ''))[:160]}"
                                                    for a in summary["alerts"][:12] if isinstance(a, dict)))
    if summary.get("colonist_list"):
        parts.append("## Colonists\n" + "\n".join(_colonist(c) for c in summary["colonist_list"] if isinstance(c, dict)))
    if steward := _steward(summary.get("steward")):
        parts.append("## Steward (sets work priorities, keeps stock targets, runs the standing orders; you direct it)\n" + "\n".join(steward))
    if summary.get("key_stocks"):
        parts.append(f"## Key stocks\n{json.dumps(summary['key_stocks'], ensure_ascii=False)[:1500]}")
    if brain_errors:
        parts.append("## Brain problems (fix them)\n" + "\n".join(f"- {k}: {_last_line(v)}" for k, v in brain_errors.items()))
    parts.append("Act now. Finish with end_turn (notes and a wake plan).")
    return Report("\n\n".join(parts), numbers, changes, summary.get("day"), summary.get("hour"))
