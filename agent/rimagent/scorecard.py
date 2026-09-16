"""Episode scoring. Honest and assisted runs are recorded separately."""
from __future__ import annotations

import json
import time
from typing import Any

from .paths import SCORES


def score_from(days: int, colonists: int, deaths: int, wealth: float, mood_avg: float, research_done: int, raids_survived: int, starting_colonists: int = 3) -> float:
    return round(
        days * 10
        + colonists * 60
        + max(0.0, wealth - 14000) / 400
        + mood_avg * 0.5
        + research_done * 8
        + raids_survived * 40
        - deaths * 120,
        1,
    )


def record(entry: dict[str, Any]) -> None:
    entry = {"t": time.time(), **entry}
    with SCORES.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def history(last: int = 20) -> list[dict[str, Any]]:
    if not SCORES.exists():
        return []
    rows = [json.loads(l) for l in SCORES.read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows[-last:]


def history_text(last: int = 12) -> str:
    rows = history(last)
    if not rows:
        return "(no episodes scored yet)"
    out = ["episode | seed | days | colonists | deaths | wealth | score | assisted | skills-sha | ended"]
    for r in rows:
        out.append(f"{r.get('episode')} | {r.get('seed')} | {r.get('days')} | {r.get('colonists')} | {r.get('deaths')} | {r.get('wealth')} | {r.get('score')} | {'yes' if r.get('assisted') else 'no'} | {str(r.get('brain_sha', ''))[:7]} | {r.get('ended')}")
    return "\n".join(out)
