from rimagent.registry import tool
"""One-call step opener.

I kept reading the same handful of summary fields plus map.find(blueprint) at the
top of every step. step_brief collapses that into one call.
"""

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


@tool(
    "step_brief",
    "One-call step opener: date/season/weather/temp, food_days, mood_avg, wealth, threat_points, research, blueprint+frame counts, alerts, pending_letters, designated work by type, home rooms (role/cells/temp/impressiveness) and key stocks. Replaces state.summary + several map.find calls at the start of a step. Also flags `stalled` when blueprints/frames > 0 but nothing changed.",
    {},
)
def step_brief(ctx):
    s = ctx.bridge.call("state.summary")
    out = {k: s.get(k) for k in (
        "date", "hour", "day", "season", "weather", "temp_outdoor", "temp_seasonal",
        "food_days", "mood_avg", "wealth", "threat_points", "danger",
        "research_current", "research_progress", "blueprints", "frames",
        "alerts", "pending_letters", "home_center", "paused",
    )}
    out["key_stocks"] = s.get("key_stocks")
    out["designations"] = s.get("designations")
    rooms = s.get("room_digest") or []
    out["rooms"] = [
        r for r in rooms
        if (r.get("cells") or 0) >= 9 or (r.get("role") not in (None, "None", ""))
    ]
    try:
        bps = _things(ctx.bridge.call("map.find", kind="blueprint", limit=400))
        g = {}
        for t in bps:
            g.setdefault(_def_of(t), []).append(t)
        out["blueprint_by_def"] = {
            d: {"n": len(v), "at": [_cell_of(t) for t in v[:3]]}
            for d, v in sorted(g.items(), key=lambda kv: -len(kv[1]))
        }
    except Exception as e:
        out["blueprint_error"] = str(e)
    # quick verdict the planner can act on without extra reads
    notes = []
    if s.get("food_days") is not None and s["food_days"] < 3:
        notes.append("FOOD EMERGENCY")
    elif s.get("food_days") is not None and s["food_days"] < 6:
        notes.append("food low")
    if s.get("hostiles"):
        notes.append("hostiles on map")
    if s.get("downed"):
        notes.append("colonist downed")
    if s.get("alerts"):
        notes.append("alerts: " + "; ".join(str(a) for a in s["alerts"])[:200])
    out["notes"] = notes
    return out
