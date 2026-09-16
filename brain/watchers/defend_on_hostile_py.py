# Reflex: the moment a hostile group appears, bias the whole colony to defend
# for 6h (zeros hunting, halves forestry/mining, pulls pawns from hunting).
# This is the one posture call I kept doing by hand on every hostile_group.
# It does NOT draft pawns (the combat order owns that) - it only sets posture.

def watch(ctx, events):
    out = []
    for e in events:
        if e.get("kind") == "hostile_group":
            out.append({
                "type": "action",
                "method": "steward.posture",
                "params": {"label": "defend", "hours": 6},
                "note": "hostile_group: auto defend posture 6h",
            })
    return out
