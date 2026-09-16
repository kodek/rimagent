def watch(ctx, events):
    """Fire when threat points are high but no turrets exist on the map.
    
    Episode 3 lesson: no power = no turrets = death against mechs.
    This watcher fires on day ticks when threat_points > 100 and no Turret_Gun
    building exists within 80 cells of home. It wakes the planner to build
    a generator + battery + turrets before the raid hits.
    """
    out = []
    for ev in events:
        if ev.get("kind") != "day":
            continue
        try:
            state = ctx.state
            threat = state.get("threat_points", 0) if state else 0
            if threat < 100:
                return out
            
            # def is a Python reserved word, use dict unpacking
            turrets = ctx.bridge.call("map.find", kind="building", **{"def": "Turret_Gun"}, radius=80, limit=5)
            turret_count = len(turrets.get("things", []))
            
            if turret_count == 0:
                out.append({
                    "type": "alert",
                    "text": (
                        f"DEFENSE GAP: threat_points={threat} but NO turrets on map. "
                        "Build a wood-fired generator + battery + 2 mini-turrets NOW. "
                        "In god mode: rw_dev_spawn(def='Turret_Gun') at the approach lane. "
                        "Cost: ~400 steel + 8 components for the full setup."
                    ),
                    "wake": True,
                })
        except Exception:
            pass
    return out
