def watch(ctx, events):
    """On day tick: if any colonist is idle (wandering/relaxing) for a full day
    and has no pending work, alert the planner to set their work priorities.

    Episode 3 pattern: Kena (builder) was idle for 3+ days because her work
    priorities were never set (she's incapable of Cooking/Growing/PlantCutting,
    so the default matrix left her with nothing to do). The fix: set
    Construction/Hauling to 1-2 on her.
    """
    out = []
    for ev in events:
        if ev.get("kind") != "day":
            continue
        try:
            pawns = ctx.bridge.call("state.pawns", filter="colonists")
        except Exception:
            continue

        for p in pawns:
            job = (p.get("job") or "").lower()
            # Idle = wandering, relaxing, or no job
            if job in ("wandering", "relaxing", "", "none", "idle"):
                name = p.get("name", "?")
                mood = p.get("mood", 0)
                out.append({
                    "type": "alert",
                    "text": (
                        f"IDLE COLONIST: {name} is {job} (mood {mood:.0f}%). "
                        "Check their work priorities (rw_ui_set_work) — they may be "
                        "incapable of the assigned work type. Set Construction/Hauling "
                        "to 1-2 if they have those skills."
                    ),
                    "wake": True,
                })
    return out
