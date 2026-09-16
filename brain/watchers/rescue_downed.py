def watch(ctx, events):
    """On colonist_downed: send the best available colonist to rescue the downed one.

    Picks a healthy, non-drafted colonist (not the downed one), preferring the
    highest Medical skill, and issues a rescue order. Wakes the planner for
    medical setup.

    Also checks if a bed exists in safe temperature before issuing the order;
    if not, alerts the planner to place a bed blueprint in safe ground first.
    """
    import re
    out = []
    for ev in events:
        if ev.get("kind") != "colonist_downed":
            continue
        downed_name = (ev.get("text") or "").split(" ")[0]
        downed_id = ev.get("thing")

        try:
            pawns = ctx.bridge.call("state.pawns", filter="colonists")
        except Exception:
            pawns = []

        def med_score(p):
            ts = p.get("top_skills") or ""
            m = re.search(r"Medicine\s+(\d+)", ts)
            return int(m.group(1)) if m else -1

        candidates = [p for p in pawns
                      if p.get("name") != downed_name and not p.get("drafted")]
        if not candidates:
            out.append({
                "type": "alert",
                "text": f"{downed_name} downed but no healthy colonist available to rescue",
                "wake": True,
            })
            continue

        candidates.sort(key=med_score, reverse=True)
        rescuer = candidates[0]

        # Check if a bed exists (beds within radius 40 of home)
        try:
            beds = ctx.bridge.call("map.find", kind="building", **{"def": "Bed"}, limit=20)
            bed_count = len(beds.get("things") or [])
        except Exception:
            bed_count = 0

        out.append({
            "type": "action",
            "method": "ui.order",
            "params": {"pawn": rescuer["name"], "at": downed_id, "label": "rescue"},
            "note": f"{rescuer['name']} rescuing {downed_name} ({bed_count} beds found)",
        })

        if bed_count == 0:
            out.append({
                "type": "alert",
                "text": (
                    f"{downed_name} downed - NO BEDS FOUND. "
                    "Place a bed blueprint in safe ground immediately "
                    "(rw_ui_build def=Bed at a safe cell outside the fire zone). "
                    f"{rescuer['name']} is rescuing but will fail without a bed. "
                    "Check rw_state_base for TRAPPED colonists."
                ),
                "wake": True,
            })
        else:
            out.append({
                "type": "alert",
                "text": (
                    f"{downed_name} downed - {rescuer['name']} sent to rescue "
                    f"({bed_count} beds available). "
                    "If the rescue order fails: (1) check rw_state_base for TRAPPED colonists, "
                    "(2) deconstruct blocking walls if sealed, "
                    "(3) check medical policy and set Doctor priority 1."
                ),
                "wake": True,
            })
    return out
