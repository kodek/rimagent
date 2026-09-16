def watch(ctx, events):
    """On hostile_group: draft ALL violence-capable colonists and position them
    at the home center (default chokepoint). The planner repositions to the
    actual door cell from the notebook.

    With 3+ armed colonists, every shooter should be drafted. Melee-only pawns
    are drafted last. The alert tells the planner to position them at the
    chokepoint from the notebook.
    """
    out = []
    for ev in events:
        if ev.get("kind") != "hostile_group":
            continue
        try:
            pawns = ctx.bridge.call("state.pawns", filter="colonists")
        except Exception:
            pawns = []
        ranged_kw = ("rifle", "revolver", "pistol", "musket", "shotgun",
                     "bow", "crossbow", "smg", "carbine", "machine", "flamer")
        def is_ranged(w):
            w = (w or "").lower()
            return any(k in w for k in ranged_kw)
        shooters = [p for p in pawns if is_ranged(p.get("weapon"))]
        melee = [p for p in pawns if not is_ranged(p.get("weapon"))]
        picks = shooters + melee
        for p in picks:
            out.append({
                "type": "action",
                "method": "ui.draft",
                "params": {"pawn": p["name"], "drafted": True},
                "note": f"Drafted {p['name']} ({p.get('weapon') or 'melee'}) for hostile group",
            })
            # Position at home center as default; planner repositions to door cell
            out.append({
                "type": "action",
                "method": "ui.goto",
                "params": {"pawn": p["name"], "cell": "home"},
                "note": f"Positioned {p['name']} at home center (reposition to door cell)",
            })
        who = ", ".join(p["name"] for p in picks) or "no colonists"
        out.append({
            "type": "alert",
            "text": (
                f"Hostile group spotted - drafted and positioned {who} at home center. "
                "Reposition shooters to the door cell from the notebook (rw_ui_goto or position_shooters). "
                "Check rw_state_threats for count/weapons/distance. "
                "Set game speed to 1 for precise orders."
            ),
            "wake": True,
        })
    return out
