from rimagent.registry import tool
"""Production bills + corpse/meat status, and an idempotent bill ensurer.

I kept repeating: map.find(building) -> per-table state.bills -> ui.add_bill, and
twice I stacked a DUPLICATE ButcherCorpseFlesh bill. These two tools collapse that.

Verified recipe defNames (RimWorld 1.6, read from defs.get this episode):
  FueledStove / ElectricStove / Campfire : CookMealSimple (TargetCount)
  ButcherSpot                            : ButcherCorpseFlesh (Forever)
  TableStonecutter                       : Make_StoneBlocksAny (Forever)
  TableSculpting                         : Make_SculptureSmall (TargetCount)
"""

try:  # provided by the harness when loading this file
    tool
except NameError:  # local fallback so the file still imports
    def tool(name, description, args):
        def _deco(fn):
            fn._tool_meta = (name, description, args)
            return fn
        return _deco


# def -> (recipe, mode, count) that a freshly built table should carry
DESIRED = {
    "FueledStove": ("CookMealSimple", "TargetCount", 20),
    "ElectricStove": ("CookMealSimple", "TargetCount", 20),
    "Campfire": ("CookMealSimple", "TargetCount", 10),
    "ButcherSpot": ("ButcherCorpseFlesh", "Forever", 0),
    "TableStonecutter": ("Make_StoneBlocksAny", "Forever", 0),
    "TableSculpting": ("Make_SculptureSmall", "TargetCount", 3),
}
TABLES = tuple(DESIRED) + ("SimpleResearchBench",)
COOK_STOVES = ("FueledStove", "ElectricStove")


def _things(res):
    if isinstance(res, dict):
        return res.get("things") or res.get("items") or []
    return res or []


def _cells(ctx):
    out = {}
    for d in TABLES:
        try:
            for t in _things(ctx.bridge.call("map.find", kind="building", **{"def": d})):
                out.setdefault(d, []).append(t)
        except Exception:
            pass
    return out


def _bills(ctx, tid):
    try:
        b = ctx.bridge.call("state.bills", thing=tid)
        return b if isinstance(b, list) else []
    except Exception:
        return []


@tool(
    "production_status",
    "ONE call: every production table (stove/campfire/butcher/stonecutter/art bench) with its bills (recipe+mode+target and DUPLICATES flagged), plus corpses by type/rot and meat/leather stock. Replaces the repeated map.find(building)+state.bills loop.",
    {},
)
def production_status(ctx):
    out = {"tables": [], "duplicates": [], "corpses": {}}
    cells = _cells(ctx)
    stoves = any(d in cells for d in COOK_STOVES)
    for d, ts in cells.items():
        if d == "SimpleResearchBench":
            continue
        for t in ts:
            bills = _bills(ctx, t["id"])
            recs = [b.get("recipe") for b in bills]
            row = {"def": d, "id": t["id"], "at": t.get("pos"),
                   "bills": [{"recipe": b.get("recipe"), "mode": b.get("mode"),
                              "target": b.get("target"), "suspended": b.get("suspended")}
                             for b in bills]}
            out["tables"].append(row)
            dup = {r for r in recs if recs.count(r) > 1}
            if dup:
                out["duplicates"].append({"id": t["id"], "def": d, "recipes": sorted(dup)})
    # corpses: animal vs humanlike, rotting, distance
    try:
        cr = _things(ctx.bridge.call("map.find", kind="corpse", limit=60))
        anim = [c for c in cr if not c.get("def", "").startswith("Corpse_Human")]
        hum = [c for c in cr if c.get("def", "").startswith("Corpse_Human")]
        out["corpses"] = {
            "animal": len(anim), "human": len(hum),
            "animal_nearest": [{"id": c["id"], "at": c.get("pos"),
                                "rotting": c.get("rotting"), "forbidden": c.get("forbidden"),
                                "dist": c.get("dist")} for c in sorted(anim, key=lambda c: c.get("dist", 9e9))[:6]],
            "human_nearest": [{"id": c["id"], "at": c.get("pos"),
                               "rotting": c.get("rotting"), "dist": c.get("dist")}
                              for c in sorted(hum, key=lambda c: c.get("dist", 9e9))[:4]],
        }
    except Exception as e:
        out["corpses_error"] = str(e)
    # butcher bill present?
    out["butcher_bill"] = any(
        any(b.get("recipe") == "ButcherCorpseFlesh" for b in r["bills"])
        for r in out["tables"] if r["def"] == "ButcherSpot"
    )
    if not out["butcher_bill"] and out["corpses"].get("animal"):
        out["corpses"]["warning"] = "animal corpses but NO butcher bill"
    try:
        ks = ctx.bridge.call("state.summary").get("key_stocks") or {}
        out["key_stocks"] = {k: v for k, v in ks.items()
                             if k in ("Meat", "Meat_Human", "Leather", "WoodLog",
                                      "BlocksGranite", "BlocksSandstone", "Steel", "MealSimple")}
    except Exception:
        pass
    return out


@tool(
    "ensure_bills",
    "Idempotent: give every production table its standard bill if missing, and DELETE duplicate bills of the same recipe (I stacked a double ButcherCorpseFlesh once). Respects 'stove present -> no campfire cooking bill'. Run after building/ finishing any work table; returns what it added/removed.",
    {"dry_run": "default False; True to only report planned changes"},
)
def ensure_bills(ctx, dry_run=False):
    cells = _cells(ctx)
    stoves = any(d in cells for d in COOK_STOVES)
    added, removed, skipped = [], [], []
    for d, ts in cells.items():
        want = DESIRED.get(d)
        if d == "Campfire" and stoves:
            want = None
            skipped.append({"id": ts[0]["id"], "why": "stove present"})
        for t in ts:
            bills = _bills(ctx, t["id"])
            recs = [b.get("recipe") for b in bills]
            # add missing desired bill
            if want and want[0] not in recs:
                added.append({"id": t["id"], "def": d, "recipe": want[0], "mode": want[1]})
                if not dry_run:
                    ctx.bridge.call("ui.add_bill", thing=t["id"], recipe=want[0],
                                    mode=want[1], count=want[2])
            # delete duplicate bills of the same recipe (highest index first)
            seen = set()
            for idx in range(len(bills) - 1, -1, -1):
                r = recs[idx]
                if r in seen:
                    removed.append({"id": t["id"], "def": d, "recipe": r, "index": idx})
                    if not dry_run:
                        ctx.bridge.call("ui.bill", thing=t["id"], index=idx, action="delete")
                else:
                    seen.add(r)
    return {"added": added, "removed": removed, "skipped": skipped, "dry_run": dry_run}
