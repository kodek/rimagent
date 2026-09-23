"""Raid, fire or a downed colonist in the ledger: clock to 1x and wake the planner. Reacts to events only."""


def watch(events, status, memo):
    out = []
    for e in events:
        kind = e.get("kind")
        text = (e.get("text") or "")[:160]
        low = text.lower()
        if kind == "hostile_group":
            out.append({"type": "action", "method": "game.speed", "params": {"speed": 1}, "note": "raid: clock to 1x"})
            out.append({"type": "alert", "text": "RAID: " + text, "wake": True})
        elif kind == "colonist_downed":
            out.append({"type": "action", "method": "game.speed", "params": {"speed": 1}, "note": "colonist downed: clock to 1x"})
        elif kind in ("incident", "message") and ("fire" in low or "burning" in low):
            out.append({"type": "action", "method": "game.speed", "params": {"speed": 1}, "note": "fire: clock to 1x"})
            out.append({"type": "alert", "text": "FIRE: " + text, "wake": True})
        elif kind == "building_lost":
            out.append({"type": "alert", "text": "building lost: " + text, "wake": True})
    return out
