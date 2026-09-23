"""One-call reports that I used to build with many reads: defense, morale, farms, storage, builds."""
import asyncio
from dataclasses import dataclass
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import FunctionToolset

tools = FunctionToolset()
DEFENSES = ("Barricade", "Sandbag", "Trap", "Turret", "Spike", "Embrasure")
NEEDS = ("Food", "Rest", "Joy", "Beauty", "Comfort")


async def _call(ctx: RunContext, method: str, **params: Any) -> Any:
    return await ctx.deps.bridge.call(method, params)


@tools.tool
async def defense_readiness(ctx: RunContext) -> dict[str, Any]:
    """Raid check in one call: hostiles nearest first, who is armed or drafted, defenses within 35 cells of home, a verdict."""
    threats, colonists, near = await asyncio.gather(
        _call(ctx, "state.threats"), _call(ctx, "state.pawns", filter="colonists"), _call(ctx, "map.find", kind="building", radius=35, limit=400))
    hostiles = sorted(threats.get("hostiles") or [], key=lambda h: h.get("dist_home", 9999))
    defenses: dict[str, int] = {}
    for thing in near["things"]:
        if any(word in thing["def"] for word in DEFENSES):
            defenses[thing["def"]] = defenses.get(thing["def"], 0) + 1
    armed = [c["name"] for c in colonists if c.get("weapon")]
    unarmed = [c["name"] for c in colonists if not c.get("weapon")]
    closing = [h.get("name") or h.get("id") for h in hostiles if h.get("dist_home", 9999) < 40]
    verdict = ["HOSTILES CLOSING (under 40 cells): " + ", ".join(map(str, closing))] if closing else [
        "hostiles on the map, none within 40 cells" if hostiles else "no hostiles"]
    if len(armed) <= 1:
        verdict.append(f"only {len(armed)} armed colonist(s)")
    if not defenses:
        verdict.append("no barricades, sandbags, traps or turrets near home")
    return {"threat_points": threats.get("threat_points"),
            "hostiles": [{k: h.get(k) for k in ("name", "kind", "faction", "weapon", "dist_home", "health")} for h in hostiles[:10]],
            "armed": armed, "unarmed": unarmed, "drafted": [c["name"] for c in colonists if c.get("drafted")], "defenses": defenses,
            "verdict": verdict}


@tools.tool
async def morale_report(ctx: RunContext) -> list[dict[str, Any]]:
    """Per colonist: mood against the minor break threshold, the worst thoughts, key needs and health flags."""
    colonists = await _call(ctx, "state.pawns", filter="colonists")
    details = await asyncio.gather(*(_call(ctx, "state.pawn", pawn=c["id"]) for c in colonists))
    rows = []
    for brief, pawn in zip(colonists, details, strict=True):
        thresholds = pawn.get("break_thresholds") or [None]
        worst = sorted((t for t in pawn.get("thoughts") or [] if t.get("mood", 0) < 0), key=lambda t: t["mood"])[:4]
        needs = pawn.get("needs") or {}
        health = [f"{h.get('label')} ({h['part']})" if h.get("part") else str(h.get("label")) for h in pawn.get("hediffs") or []]
        health += [f"bleeding {pawn['bleeding']}"] if pawn.get("bleeding") else []
        health += ["needs tending"] if pawn.get("needs_tending") else []
        row = {"name": brief["name"], "mood": brief.get("mood"), "break_at": thresholds[0], "worst_thoughts": [f"{t['label']} {t['mood']:+g}" for t in worst],
               "needs": {k: needs[k] for k in NEEDS if k in needs}, "health": health}
        if row["mood"] is not None and row["break_at"] is not None and row["mood"] < row["break_at"] + 6:
            row["ALERT"] = f"mood {row['mood']} is near the break threshold {row['break_at']}"
        rows.append(row)
    return rows


@tools.tool
async def farm_report(ctx: RunContext) -> dict[str, Any]:
    """Growing zones and, per crop: plants, mean growth, ready to harvest, days to ripe; empty cells; food days."""
    summary = await _call(ctx, "state.summary")
    zones = [z for z in summary.get("zones") or [] if str(z.get("type", "")).startswith("growing:")]
    crops = sorted({z["type"].split(":", 1)[1] for z in zones} - {"", "None"})
    found = await asyncio.gather(*(_call(ctx, "map.find", **{"def": crop, "limit": 600}) for crop in crops))
    days = await asyncio.gather(*(_call(ctx, "engine.get", path=f"Def:ThingDef:{crop}.plant.growDays", depth=0) for crop in crops))
    rows = []
    for crop, result, grow_days in zip(crops, found, days, strict=True):
        growth = [t["growth"] for t in result["things"] if t.get("growth") is not None]
        mean = round(sum(growth) / len(growth), 2) if growth else None
        rows.append({"crop": crop, "plants": result["count"], "mean_growth": mean, "ready": sum(1 for t in result["things"] if t.get("harvestable")),
                     "grow_days": grow_days, "days_to_ripe": round((1 - mean) * grow_days, 1) if mean is not None and isinstance(grow_days, int | float) else None})
    cells, plants = sum(z.get("cells", 0) for z in zones), sum(r["plants"] for r in rows)
    notes = [f"{cells - plants} of {cells} growing cells are empty"] if cells and plants < 0.9 * cells else []
    notes += [f"ready to harvest: {r['crop']} x{r['ready']}" for r in rows if r["ready"]]
    return {"food_days": summary.get("food_days"), "season": summary.get("season"), "growing_now": summary.get("growing_now"),
            "zones": [{"label": z.get("label"), "crop": z["type"].split(":", 1)[1], "cells": z.get("cells"), "at": z.get("at")} for z in zones],
            "crops": rows, "notes": notes}


@tools.tool
async def storage_report(ctx: RunContext) -> dict[str, Any]:
    """Stockpiles and shelves, and what lies outside storage (loose, forbidden, rotting, unroofed), with notes."""
    storage, summary = await asyncio.gather(_call(ctx, "state.storage"), _call(ctx, "state.summary"))
    outside = summary.get("outside_storage") or {}
    notes = [] if storage else ["NO STOCKPILES"]
    if outside.get("rotting"):
        notes.append(f"{outside['rotting']} stacks rot outside storage")
    if outside.get("forbidden"):
        notes.append(f"{outside['forbidden']} loose stacks are forbidden (unforbid them to haul)")
    if outside.get("unroofed_deteriorating", 0) >= 10:
        notes.append(f"{outside['unroofed_deteriorating']} stacks deteriorate without a roof")
    if outside.get("storage_cells_free") is not None and outside["storage_cells_free"] <= 4:
        notes.append(f"storage is nearly full ({outside['storage_cells_free']} cells free)")
    return {"storage": storage, "outside": outside, "notes": notes or ["storage OK"]}


@tools.tool
async def build_report(ctx: RunContext) -> dict[str, Any]:
    """Blueprints and frames by def with sample cells, the designations, and the key material stocks."""
    planned, designations, summary = await asyncio.gather(
        _call(ctx, "map.find", kind="blueprint", limit=500), _call(ctx, "state.designations"), _call(ctx, "state.summary"))
    by_def: dict[str, list[Any]] = {}
    for thing in planned["things"]:
        by_def.setdefault(thing["def"], []).append(thing.get("pos"))
    return {"planned": {d: {"count": len(cells), "at": cells[:3]} for d, cells in sorted(by_def.items(), key=lambda kv: -len(kv[1]))},
            "designations": designations, "key_stocks": summary.get("key_stocks")}


@dataclass
class ColonyReports(AbstractCapability):
    def get_toolset(self):
        return tools
