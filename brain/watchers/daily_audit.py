"""Once per in-game day, run the checks I kept doing by hand every few steps:
food_days, mood_avg, and whether the build queue has stalled. Also nags about
rotting loose stacks. One state.summary call per day event, nothing else.

Thresholds are the doctrine ones: food < 4 days is the top task, mood < 38 is
break territory. A build that is unchanged across a whole day means no builder
or no material (the trap I hit twice).
"""

_PREV = {"bp": None, "stall": 0}


def watch(ctx, events):
    out = []
    if not any(e.get("kind") == "day" for e in events):
        return out
    try:
        s = ctx.bridge.call("state.summary") or {}
    except Exception as e:
        return [{"type": "alert", "text": "daily_audit: read failed: %s" % e, "wake": False}]

    fd = s.get("food_days")
    if fd is not None and fd < 4:
        out.append({"type": "alert", "text": "DAILY: food_days %.1f (<4)" % fd, "wake": True})

    mood = s.get("mood_avg")
    if mood is not None and mood < 38:
        out.append({"type": "alert", "text": "DAILY: mood_avg %.0f (<38)" % mood, "wake": True})

    os_ = s.get("outside_storage") or {}
    rot = os_.get("rotting") or 0
    if rot >= 5:
        out.append({"type": "alert", "text": "DAILY: %d stacks rotting outside" % rot, "wake": False})

    bp = (s.get("blueprints") or 0) + (s.get("frames") or 0)
    if bp > 0:
        if _PREV["bp"] == bp:
            _PREV["stall"] += 1
        else:
            _PREV["stall"] = 0
        if _PREV["stall"] >= 1:
            out.append({"type": "alert",
                        "text": "DAILY: build stalled at %d blueprints/frames" % bp,
                        "wake": True})
    else:
        _PREV["stall"] = 0
    _PREV["bp"] = bp
    return out
