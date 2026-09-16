def watch(ctx, events):
    """On day tick: check for corpses within 30 cells of home.
    Any corpse near the base causes mood drag. Alert when found so the
    planner can designate haul-to-dump or destroy.
    """
    out = []
    if not any(isinstance(e, dict) and e.get("kind") == "day" for e in events):
        return out

    try:
        corpses = ctx.bridge.call(
            "map.find",
            kind="corpse",
            radius=30,
            limit=20,
        )
    except Exception:
        return out

    things = (corpses or {}).get("things", [])
    if not things:
        return out

    ids = [c.get("id", "?") for c in things if isinstance(c, dict)]
    out.append({
        "type": "alert",
        "text": (
            f"{len(ids)} corpse(s) within 30 cells of home: {', '.join(ids)}. "
            "Rotting corpses cause -6 mood to all colonists. "
            "Use check_degradation to see HP, then designate haul or destroy."
        ),
        "wake": True,
    })
    return out
