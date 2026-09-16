def watch(ctx, events):
    """On day tick: if any colonist is idle (wandering/relaxing/sitting) for a full
    day and has no pending work, alert the planner to set their work priorities.

    Episode 3 pattern: Kena (builder) was idle for 3+ days because her work
    priorities were never set. The fix: set Construction/Hauling to 1-2 on her.

    Idle job names in RimWorld (JobDef defName, lowercased):
    wander, relax, sit, stand, laydown, sleep
    """
    IDLE_JOBS = {"wander", "relax", "sit", "stand", "laydown", "sleep", "", "none", "idle"}
    out = []
    for ev in events:
        if not isinstance(ev, dict) or ev.get("kind") != "day":
            continue
        try:
            pawns = ctx.bridge.call("state.pawns", filter="colonists")
        except Exception:
            continue

        for p in pawns:
            if not isinstance(p, dict):
                continue
            job = (p.get("job") or "").lower()
            if job in IDLE_JOBS:
                name = p.get("name", "?")
                mood = p.get("mood", 0)
                out.append({
                    "type": "alert",
                    "text": (
                        f"IDLE COLONIST: {name} is {job or 'idle'} (mood {mood:.0f}%). "
                        "Check their work priorities (rw_ui_set_work) — they may be "
                        "incapable of the assigned work type. Set Construction/Hauling "
                        "to 1-2 if they have those skills."
                    ),
                    "wake": True,
                })
    return out
