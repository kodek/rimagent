"""A pawn sleeping outside, on the ground or in the cold, or a missing bed: a half-finished shelter costs mood.
Note: a door left as a frame keeps a room outdoors even when every wall is built."""

PHRASES = ("slept outside", "slept on the ground", "slept in the cold", "slept in the heat", "needs a bed", "wants a bed")


def watch(events, status, memo):
    out = []
    for e in events:
        text = e.get("text") or ""
        if e.get("kind") in ("message", "incident", "letter") and any(p in text.lower() for p in PHRASES):
            out.append({"type": "alert", "text": "SHELTER/SLEEP: " + text[:140], "wake": True})
    return out
