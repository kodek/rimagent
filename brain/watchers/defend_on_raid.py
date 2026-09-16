def watch(ctx, events):
    """Automatically sets a defensive posture for 6 hours when a hostile group appears."""
    out = []
    for ev in events:
        if not isinstance(ev, dict) or ev.get("kind") != "hostile_group":
            continue
        out.append({
            "type": "action",
            "method": "steward.posture",
            "params": {"label": "defend", "hours": 6},
            "note": f"Automated defense posture triggered by {ev.get('kind')}: {ev.get('text')}",
        })
    return out
