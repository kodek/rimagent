def watch(ctx, events):
    """On day tick, colonist_downed, OR mental_break: check every colonist's mood
    against their major-break threshold, INCLUDING the catharsis-fade crash.

    The catharsis-fade crash is the #1 off-guard pattern: after a mental break a
    colonist gets a +40 (major/extreme) or +30 (minor) catharsis buff that fades
    over ~2 days. While it's active their displayed mood looks fine (e.g. 50%)
    even though the underlying debuff is still there. When the buff fades, mood
    crashes and can cross the major threshold.

    Fires on:
      - day tick (routine check)
      - colonist_downed (a downed colonist at low mood will break on waking)
      - mental_break (the break just happened; check the OTHER colonists for
        catharsis crashes and the breaker's post-break state)
    """
    out = []
    check_all = False
    for ev in events:
        kind = ev.get("kind")
        if kind in ("day", "colonist_downed", "mental_break"):
            check_all = True
    if not check_all:
        return out

    try:
        pawns = ctx.bridge.call("state.pawns", filter="colonists")
    except Exception:
        return out

    for p in pawns:
        name = p.get("name")
        raw_mood = p.get("mood")
        if raw_mood is None:
            continue

        # major-break threshold (fraction 0-1 from engine; convert to percentage)
        threshold = None
        try:
            t = ctx.bridge.call(
                "engine.get",
                path=f"Pawn:{name}.mindState.mentalBreaker.BreakThresholdMajor",
            )
            if isinstance(t, (int, float)):
                threshold = t * 100
        except Exception:
            pass
        if threshold is None:
            threshold = 27.0  # Losing is Fun + neurotic fallback

        # catharsis value from per-pawn thoughts
        catharsis = 0
        try:
            detail = ctx.bridge.call("state.pawn", pawn=name)
            for t in (detail.get("thoughts") or []):
                label = (t.get("label") or "").lower()
                key = (t.get("thought") or "").lower()
                if "catharsis" in label or "catharsis" in key:
                    v = t.get("mood")
                    if isinstance(v, (int, float)):
                        catharsis = max(catharsis, v)
                    break
        except Exception:
            pass

        post_fade = raw_mood - catharsis
        if raw_mood < threshold:
            out.append({
                "type": "alert",
                "text": (
                    f"MOOD CRISIS: {name} at {raw_mood:.0f}% (major threshold "
                    f"{threshold:.0f}%). Run mood_triage and fix the "
                    f"biggest negative thought now."
                ),
                "wake": True,
            })
        elif catharsis > 0 and post_fade < threshold:
            out.append({
                "type": "alert",
                "text": (
                    f"CATHARSIS CRASH IMMINENT: {name} looks fine at {raw_mood:.0f}% "
                    f"but has +{catharsis:.0f} catharsis that will fade -> post-fade "
                    f"~{post_fade:.0f}% (< major threshold {threshold:.0f}%). "
                    f"Fix the underlying debuff NOW. Run mood_triage."
                ),
                "wake": True,
            })
    return out
