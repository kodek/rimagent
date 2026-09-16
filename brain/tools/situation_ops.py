"""One-call situation reads I kept rebuilding by hand.

`defense_readiness`: threat list + our armed/drafted colonists + defensive
structures near home, with a plain verdict. Replaces rw_state_threats +
rw_state_pawns + map.find(building) at the top of every raid step.

`storage_report`: stockpiles + the summary's outside_storage overflow picture
(stacks / forbidden / rotting / unroofed_deteriorating / corpses / free cells)
with a verdict. Replaces rw_state_storage + guessing from key_stocks.
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
    "defense_readiness",
    "One call: hostiles (kind/id/distance/faction/weapon, sorted nearest-first), whether any is within 40 tiles, our colonists with weapon + drafted + mood, armed vs unarmed, and nearby barricade/trap/turret/sandbag counts, plus a verdict. Replaces state.threats + state.pawns + map.find(building) in a raid step.",
    {},
)
def defense_readiness(ctx):
    out = {}
    try:
        s = _call(ctx, "state.summary") or {}
    except Exception as e:
        return {"error": str(e)}
    home = s.get("home_center")
    out["date"] = s.get("date")
    out["danger"] = s.get("danger")
    out["threat_points"] = s.get("threat_points")
    out["hostile_n"] = s.get("hostiles")

    t = {}
    try:
        t = _call(ctx, "state.threats") or {}
    except Exception as e:
        out["threats_error"] = str(e)
    hosts = _as_list(t, "hostiles")
    hosts.sort(key=lambda h: (h.get("dist_home") if h.get("dist_home") is not None else 9999))
    out["hostiles"] = [{
        "kind": h.get("kind"), "id": h.get("id"), "dist": h.get("dist_home"),
        "faction": h.get("faction"), "weapon": h.get("weapon"),
        "fogged": h.get("fogged"),
    } for h in hosts[:10]]
    out["closing"] = [h["id"] for h in out["hostiles"]
                      if (h.get("dist") if h.get("dist") is not None else 9999) < 40]

    pawns = []
    try:
        p = _call(ctx, "state.pawns", filter="colonists")
        pawns = _as_list(p, "pawns", "colonists", "things")
    except Exception as e:
        out["pawns_error"] = str(e)
    out["colonists"] = [{
        "name": p.get("name"), "weapon": p.get("weapon"),
        "drafted": p.get("drafted"), "mood": p.get("mood"),
    } for p in pawns]
    out["armed"] = [p["name"] for p in out["colonists"] if p.get("weapon")]
    out["unarmed"] = [p["name"] for p in out["colonists"] if not p.get("weapon")]

    try:
        bres = _call(ctx, "map.find", kind="building", near=home, radius=35, limit=400)
        things = _as_list(bres, "things", "items")
        want = ("Barricade", "Sandbag", "Trap", "Turret", "Spike", "Stool", "Barbed")
        counts = {}
        for th in things:
            d = th.get("def") or th.get("defName") or ""
            if any(w in d for w in want):
                counts[d] = counts.get(d, 0) + 1
        out["defenses"] = counts
    except Exception as e:
        out["defenses_error"] = str(e)

    notes = []
    if out["closing"]:
        notes.append("HOSTILE CLOSING (<40 tiles): " + ",".join(out["closing"]))
    elif out["hostiles"]:
        notes.append("hostiles on map, none within 40 tiles")
    else:
        notes.append("no hostiles")
    if len(out["armed"]) <= 1:
        notes.append("only %d armed colonist(s)" % len(out["armed"]))
    if out["unarmed"]:
        notes.append("unarmed: " + ",".join(out["unarmed"]))
    out["notes"] = notes
    return out


@tool(
    "storage_report",
    "One call: every stockpile zone (name/priority/cells/items/at), free storage cells, and the summary's outside_storage overflow picture (loose stacks, forbidden, rotting, unroofed_deteriorating, corpses, by_category) with a verdict. Replaces rw_state_storage plus guessing from key_stocks.",
    {},
)
def storage_report(ctx):
    out = {}
    try:
        s = _call(ctx, "state.summary") or {}
    except Exception as e:
        return {"error": str(e)}
    try:
        zones = _as_list(_call(ctx, "state.storage"), "zones", "storage")
    except Exception as e:
        zones = []
        out["zones_error"] = str(e)
    out["zones"] = zones
    os_ = s.get("outside_storage") or {}
    out["outside"] = os_
    notes = []
    if not zones:
        notes.append("NO STOCKPILE ZONES")
    rot = os_.get("rotting") or 0
    unroof = os_.get("unroofed_deteriorating") or 0
    forb = os_.get("forbidden") or 0
    free = os_.get("storage_cells_free")
    if rot:
        notes.append("%d stacks rotting OUTSIDE" % rot)
    if forb:
        notes.append("%d forbidden loose stacks (unforbid to haul)" % forb)
    if unroof >= 10:
        notes.append("%d unroofed, deteriorating" % unroof)
    if free is not None and free <= 4:
        notes.append("stockpiles nearly full (%s cells free)" % free)
    if (os_.get("stacks") or 0) >= 20 and not notes:
        notes.append("%d loose stacks outside stockpiles" % os_.get("stacks"))
    out["notes"] = notes or ["storage OK"]
    return out
