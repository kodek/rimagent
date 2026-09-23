"""Once per in-game day: food days, mood, rotting stacks, and a build queue that stalled for a whole day.
Food under 4 days is the top task; mood under 38 is break territory."""


async def watch(events, status, memo):
    out = []
    if not any(e.get("kind") == "day" for e in events):
        return out
    s = await rpc("state.summary", {}) or {}
    food = s.get("food_days")
    if food is not None and food < 4:
        out.append({"type": "alert", "text": "DAILY: food_days %.1f (<4)" % food, "wake": True})
    mood = s.get("mood_avg")
    if mood is not None and mood < 38:
        out.append({"type": "alert", "text": "DAILY: mood_avg %.0f (<38)" % mood, "wake": True})
    rotting = (s.get("outside_storage") or {}).get("rotting") or 0
    if rotting >= 5:
        out.append({"type": "alert", "text": "DAILY: %d stacks rotting outside" % rotting, "wake": False})
    queued = (s.get("blueprints") or 0) + (s.get("frames") or 0)
    stalled = queued > 0 and memo.get("queued") == queued
    memo["stall"] = memo.get("stall", 0) + 1 if stalled else 0
    memo["queued"] = queued
    if memo["stall"] >= 1:
        out.append({"type": "alert", "text": "DAILY: build stalled at %d blueprints/frames" % queued, "wake": True})
    return out
