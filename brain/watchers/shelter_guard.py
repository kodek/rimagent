"""Non-combat regressions the raid/fire watcher ignores: a pawn sleeping outside /
on the ground / in the cold, or a missing-bed alert. These are how a half-finished
shelter silently costs mood. Cheap: reacts to ledger text, no polling.

Note: `room()` and `ui.build` returning "placed" with no failures does NOT mean the
room is enclosed (a Door left as a frame keeps it "outdoors"). This watcher is the
safety net for exactly that mistake.
"""


def watch(ctx, events):
    out = []
    for e in events:
        kind = e.get("kind")
        text = (e.get("text") or "")
        low = text.lower()
        if kind in ("message", "incident", "letter") and any(
            p in low for p in (
                "slept outside", "slept on the ground", "slept in the cold",
                "slept in the heat", "needs a bed", "wants a bed",
            )
        ):
            out.append({"type": "alert",
                        "text": "SHELTER/SLEEP: " + text[:140], "wake": True})
    return out
