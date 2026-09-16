# Reflex: when a colonist is downed, set their medical care to Best so a doctor
# tends them with the best medicine (the #1 early killer is infection/bleeding
# on a NormalOrWorse policy). This is the per-patient override I kept doing by
# hand (rw_ui_set_policies 7x). The `policies` order's default is NormalOrWorse;
# a manual set pauses that order for THIS pawn for 2 days, which is exactly what
# an injured patient needs. It does NOT draft, rescue or carry - the combat and
# rescue orders own those.

def _pawn_ref(e):
    d = e.get("data") or {}
    for k in ("pawn", "pawn_id", "id", "name"):
        if k in d:
            return d[k]
    # fall back to thing if present
    if e.get("thing"):
        return e["thing"]
    return None

def watch(ctx, events):
    out = []
    for e in events:
        if e.get("kind") in ("colonist_downed", "colonist_died"):
            ref = _pawn_ref(e)
            if ref:
                out.append({
                    "type": "action",
                    "method": "ui.set_policies",
                    "params": {"pawn": ref, "medical": "Best"},
                    "note": "%s: auto Best medical care" % e.get("kind"),
                })
            else:
                out.append({
                    "type": "alert",
                    "text": "colonist downed/died, could not identify pawn - set Best medical manually",
                    "wake": True,
                })
    return out
