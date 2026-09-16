def watch(ctx, events):
    """On day tick: if any pending Hunt designation targets an animal 30+ cells from
    home AND the colony has fewer than 2 armed colonists, alert the planner.

    Episode 2 lesson: Onesan died at 61 cells from base when a cougar found her.
    Rule: never send a hunter more than 30 cells from home unless a second armed
    pawn can respond. This watcher fires on day ticks so the planner can cancel
    unsafe hunts before a colonist walks out.
    """
    out = []
    for ev in events:
        if ev.get("kind") != "day":
            continue
        try:
            s = ctx.bridge.call("state.summary")
        except Exception:
            continue

        # Count armed colonists (Shooting skill >= 1 or has a ranged weapon)
        armed = 0
        try:
            pawns = ctx.bridge.call("state.pawns", filter="colonists")
            for p in pawns:
                skills = p.get("skills") or {}
                shooting = skills.get("Shooting", 0)
                if shooting >= 1:
                    armed += 1
        except Exception:
            pass

        if armed < 2:
            # Check pending designations for Hunt
            try:
                desig = ctx.bridge.call("state.designations")
            except Exception:
                continue

            hunt_count = 0
            for d in (desig.get("designations") or []):
                if d.get("kind") == "Hunt" or d.get("type") == "Hunt":
                    hunt_count += 1

            if hunt_count > 0:
                out.append({
                    "type": "alert",
                    "text": (
                        f"HUNT RISK: {hunt_count} pending hunt designations but only "
                        f"{armed} armed colonist(s). If any target is 30+ cells from "
                        "home, cancel them (rw_ui_designate cancel) or wait for a "
                        "second armed pawn. Episode 2: Onesan died at 61 cells."
                    ),
                    "wake": True,
                })
    return out
