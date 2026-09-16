from rimagent.registry import tool
"""Colony operations helpers: one-call build/food reports and a layout builder.

These wrap the multi-call sequences I kept repeating by hand (find blueprints ->
group by def -> read stocks; find walls -> dry_run -> build -> door -> beds).
"""

import json

try:  # provided by the harness when loading this file
    tool
except NameError:  # local fallback so the file still imports
    def tool(name, description, args):
        def _deco(fn):
            fn._tool_meta = (name, description, args)
            return fn
        return _deco


def _things(res):
    if isinstance(res, dict):
        return res.get("things") or res.get("items") or []
    return res or []


def _def_of(t):
    return t.get("def") or t.get("defName") or t.get("thingDef") or "?"


def _cell_of(t):
    return t.get("pos") or t.get("cell") or t.get("position")


def _group(things):
    g = {}
    for t in things:
        g.setdefault(_def_of(t), []).append(t)
    return g


@tool(
    "build_report",
    "Build progress in ONE call: pending blueprints grouped by def (count + sample cells), finished buildings by def, key material stocks and food_days. Replaces the repeated state.summary + map.find(blueprint) + map.find(building) sequence.",
    {},
)
def build_report(ctx):
    s = ctx.bridge.call("state.summary")
    out = {
        "date": s.get("date"),
        "food_days": s.get("food_days"),
        "key_stocks": s.get("key_stocks"),
    }
    try:
        bps = _things(ctx.bridge.call("map.find", kind="blueprint", limit=500))
        out["blueprints_total"] = len(bps)
        out["blueprints"] = {
            d: {"n": len(v), "samples": [_cell_of(t) for t in v[:3]]}
            for d, v in sorted(_group(bps).items(), key=lambda kv: -len(kv[1]))
        }
    except Exception as e:
        out["blueprints_error"] = str(e)
    try:
        bld = _things(ctx.bridge.call("map.find", kind="building", limit=800))
        out["buildings"] = {
            d: len(v) for d, v in sorted(_group(bld).items(), key=lambda kv: -len(kv[1]))
        }
    except Exception as e:
        out["buildings_error"] = str(e)
    try:
        out["designations"] = ctx.bridge.call("state.designations")
    except Exception as e:
        out["designations_error"] = str(e)
    ctx.log(json.dumps(out)[:1800])
    return out


@tool(
    "room",
    "Build an enclosing wall rect PLUS a door PLUS optional beds inside in ONE ui.build_many call (always passes `stuff`, which ui.build requires). dry_run=True (default) reports per-op failures without placing anything.",
    {
        "x": "min x",
        "z": "min z",
        "w": "width in cells",
        "h": "height in cells",
        "door": "which wall side: N|S|E|W (default S)",
        "stuff": "ThingDef, e.g. WoodLog or BlocksGranite (default WoodLog)",
        "beds": "how many beds to place inside along the west wall",
        "bed_rot": "bed rotation N|E|S|W (default E)",
        "dry_run": "default True; set False to actually place",
    },
)
def room(ctx, x, z, w, h, door="S", stuff="WoodLog", beds=0, bed_rot="E", dry_run=True):
    x, z, w, h = int(x), int(z), int(w), int(h)
    door = str(door).upper()
    dc = {
        "S": [x + w // 2, z],
        "N": [x + w // 2, z + h - 1],
        "W": [x, z + h // 2],
        "E": [x + w - 1, z + h // 2],
    }.get(door, [x + w // 2, z])
    ops = [
        {"def": "Wall", "rect": [x, z, w, h], "stuff": stuff},
        {"def": "Door", "at": dc, "stuff": stuff},
    ]
    for i in range(int(beds)):
        ops.append({"def": "Bed", "at": [x + 1, z + 1 + 2 * i], "rot": bed_rot, "stuff": stuff})
    if dry_run:
        res = []
        for op in ops:
            try:
                r = ctx.bridge.call("ui.build", dry_run=True, **op)
                res.append({"op": op, "placed": r.get("placed"), "failed": r.get("failed")})
            except Exception as e:
                res.append({"op": op, "error": str(e)})
        return {"door_cell": dc, "ops": res}
    return ctx.bridge.call("ui.build_many", ops=ops)


@tool(
    "food_report",
    "Food situation in ONE call: food_days, foods by def, and the current bills on campfires/stoves. Use when deciding whether to cook, sow or buy food.",
    {},
)
def food_report(ctx):
    s = ctx.bridge.call("state.summary")
    out = {"food_days": s.get("food_days"), "key_stocks": s.get("key_stocks")}
    try:
        out["foods"] = ctx.bridge.call("state.stocks", category="Foods")
    except Exception as e:
        out["foods_error"] = str(e)
    cooking = []
    for d in ("Campfire", "FueledStove", "ElectricStove"):
        try:
            for t in _things(ctx.bridge.call("map.find", kind="building", **{"def": d})):
                tid = t.get("id")
                try:
                    bills = ctx.bridge.call("state.bills", thing=tid)
                except Exception as e:
                    bills = str(e)
                cooking.append({"station": d, "id": tid, "bills": bills})
        except Exception:
            pass
    out["cooking"] = cooking
    return out
