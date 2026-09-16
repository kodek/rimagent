def watch(ctx, events):
    """On day tick: check for rotting corpses within 30 cells of home.
    Rotting corpses cause -6 mood to ALL colonists (ObservedRottingCorpse).
    Alert when found so the planner can designate haul-to-dump.
    """
    out = []
    if not any(e.get("kind") == "day" for e in events):
        return out

    try:
        # Find corpses near home
        corpses = ctx.bridge.call(
            "map.find",
            kind="corpse",
            radius=30,
            limit=20,
        )
    except Exception:
        return out

    rotting = []
    for c in corpses.get("things", []):
        cid = c.get("id")
        # Check if rotting: look for hediff or just check if it's an animal corpse
        # (animal corpses rot faster than human; any corpse within 30 cells is a risk)
        try:
            # Check HP - rotting items have degrading HP
            hp = ctx.bridge.call("engine.get", path=f"Thing:{cid}.maxHitPoints")
            cur_hp = ctx.bridge.call("engine.get", path=f"Thing:{cid}.hitPoints")
            if cur_hp is not None and hp is not None and cur_hp < hp * 0.9:
                rotting.append({"id": cid, "pos": c.get("pos"), "hp": f"{cur_hp:.0f}/{hp:.0f}"})
        except Exception:
            # If we can't check HP, still flag it (conservative)
            rotting.append({"id": cid, "pos": c.get("pos"), "hp": "unknown"})

    if rotting:
        ids = ", ".join(r["id"] for r in rotting)
        out.append({
            "type": "alert",
            "text": (
                f"{len(rotting)} rotting corpse(s) within 30 cells of home: {ids}. "
                "Each causes -6 mood to all colonists. Designate haul to dump zone now. "
                "Use: rw_ui_designate(designator='haul', things=[ids]) or check if a dump zone exists nearby."
            ),
            "wake": True,
        })
    return out
