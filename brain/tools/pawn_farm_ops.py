"""One-call readouts for the two things I rebuilt by hand almost every step.

`morale_report`: per colonist mood vs break threshold, the worst thoughts that
are actually driving it (SleptInCold / AteWithoutTable / DullBarracks ...),
needs, and health flags (bleeding / pain / hediffs / needs_tending). Replaces
the rw_state_pawn + repeated engine.get mood/hediff poking (13 engine_get calls
last pass, 3 of them errors).

`farm_report`: every growing zone (plant + cells) plus, per crop, planted /
avg growth / harvest-ready counts, time-to-ripe, and food_days. Replaces
map.find(kind=plant) + engine growth reads before every harvest decision.
"""

try:  # provided by the harness when loading this file
    from rimagent.registry import tool
except Exception:  # local fallback so the file still imports
    def tool(name, description, args):
        def _deco(fn):
            fn._tool_meta = (name, description, args)
            return fn
        return _deco


def _call(ctx, method, **params):
    return ctx.bridge.call(method, **params)


def _as_list(res, *keys):
    if isinstance(res, dict):
        for k in keys:
            v = res.get(k)
            if isinstance(v, list):
                return v
        return []
    if isinstance(res, list):
        return res
    return []


@tool(
    "morale_report",
    "One call: per colonist mood vs break threshold, the top NEGATIVE thoughts driving it, key needs (Food/Rest/Beauty/Comfort/Joy), and health flags (bleeding/pain/hediffs/needs_tending). Replaces the state.pawn + engine.get mood/hediff loop.",
    {},
)
def morale_report(ctx):
    out = {}
    try:
        s = _call(ctx, "state.summary") or {}
        out["mood_avg"] = s.get("mood_avg")
    except Exception:
        out["mood_avg"] = None
    pawns = _as_list(_call(ctx, "state.pawns", filter="colonists"), "pawns", "colonists")
    rows = []
    for p in pawns:
        name = p.get("name")
        row = {"name": name, "mood": p.get("mood"), "job": p.get("job")}
        try:
            d = _call(ctx, "state.pawn", pawn=name) or {}
        except Exception as e:
            row["error"] = str(e)
            rows.append(row)
            continue
        row["mood"] = d.get("mood")
        bt = d.get("break_thresholds") or []
        row["break_at"] = bt[0] if bt else None
        needs = d.get("needs") or {}
        row["needs"] = {k: needs.get(k) for k in
                        ("Food", "Rest", "Beauty", "Comfort", "Joy")
                        if k in needs}
        th = d.get("thoughts") or []
        neg = sorted([t for t in th if (t.get("mood") or 0) < 0],
                     key=lambda t: t.get("mood") or 0)[:4]
        row["worst_thoughts"] = [(t.get("label"), t.get("mood")) for t in neg]
        flags = []
        if d.get("bleeding"):
            flags.append("bleeding %.1f" % d["bleeding"])
        if d.get("pain"):
            flags.append("pain %.0f" % d["pain"])
        if d.get("needs_tending"):
            flags.append("needs tending")
        for h in (d.get("hediffs") or []):
            lab = h.get("label") or h.get("def")
            flags.append(lab if h.get("part") is None else "%s (%s)" % (lab, h.get("part")))
        row["health"] = flags
        m = row.get("mood")
        if m is not None and row.get("break_at") is not None and m < row["break_at"] + 6:
            row["ALERT"] = "mood %s near break %.0f" % (m, row["break_at"])
        rows.append(row)
    out["colonists"] = rows
    return out


@tool(
    "farm_report",
    "One call: every growing zone (plant def + cells), and per crop: planted / avg growth / harvest-ready counts, grow-days, plus food_days. Replaces map.find(kind=plant) + engine growth reads before a harvest/sow decision.",
    {},
)
def farm_report(ctx):
    out = {}
    try:
        s = _call(ctx, "state.summary") or {}
        out["food_days"] = s.get("food_days")
        out["season"] = s.get("season")
        out["growing_now"] = s.get("growing_now")
    except Exception as e:
        out["summary_error"] = str(e)

    zones = _as_list(_call(ctx, "engine.get", path="Map.zoneManager.AllZones"))
    grow = []
    for z in zones:
        if z.get("type") != "Zone_Growing":
            continue
        lab = z.get("zone")
        pd = None
        allow = None
        try:
            dz = _call(ctx, "engine.get", path="Zone:%s" % lab, depth=1) or {}
            pd = dz.get("PlantDefToGrow")
            allow = dz.get("allowSow")
        except Exception:
            pass
        grow.append({"zone": lab, "cells": z.get("cells"), "plant": pd, "allowSow": allow})
    out["growing_zones"] = grow

    defs = sorted({g["plant"] for g in grow if g.get("plant")})
    crops = []
    for d in defs:
        try:
            res = _call(ctx, "map.find", kind="plant", **{"def": d, "limit": 600})
        except Exception as e:
            crops.append({"crop": d, "error": str(e)})
            continue
        things = _as_list(res, "things", "items")
        n = len(things)
        growths = [t.get("growth") for t in things if t.get("growth") is not None]
        ready = sum(1 for t in things if t.get("harvestable"))
        gd = None
        try:
            gd = _call(ctx, "engine.get", path="Def:ThingDef:%s.plant.growDays" % d)
        except Exception:
            pass
        avg = (sum(growths) / len(growths)) if growths else None
        row = {"crop": d, "planted": n,
               "avg_growth": (round(avg, 2) if avg is not None else None),
               "harvest_ready": ready}
        if gd:
            row["grow_days"] = gd
            if avg is not None:
                row["days_to_ripe"] = round(max(0.0, (1.0 - avg)) * gd, 1)
        crops.append(row)
    out["crops"] = crops
    sown = sum(g.get("cells") or 0 for g in grow)
    planted = sum(c.get("planted") or 0 for c in crops)
    out["cells_sown"] = sown
    out["cells_planted"] = planted
    notes = []
    if sown and planted < sown * 0.9:
        notes.append("%d/%d growing-zone cells empty (sow, or a blocked cell)"
                     % (sown - planted, sown))
    if any(c.get("harvest_ready") for c in crops):
        notes.append("HARVEST READY: " + ",".join(
            "%s x%d" % (c["crop"], c["harvest_ready"]) for c in crops
            if c.get("harvest_ready")))
    fd = out.get("food_days")
    if fd is not None and fd < 4:
        notes.append("food_days %.1f LOW" % fd)
    out["notes"] = notes or ["farms OK"]
    return out
