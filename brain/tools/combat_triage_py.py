from rimagent.registry import tool
import json

def _colonists(ctx):
    try:
        r = ctx.bridge.call("state.pawns", filter="colonists")
        return r if isinstance(r, list) else []
    except Exception:
        return []

def _threats(ctx):
    try:
        r = ctx.bridge.call("state.threats")
        return r if isinstance(r, dict) else {}
    except Exception:
        return {}

def _summary(ctx):
    try:
        r = ctx.bridge.call("state.summary")
        return r if isinstance(r, dict) else {}
    except Exception:
        return {}

@tool("combat_triage",
      "One-call combat+health triage: threat danger, hostiles (dist/lord/fogged), "
      "colonists (health/downed/bleeding/mood/weapon/tending), and a verdict with "
      "recommended actions. Use INSTEAD of the 3-call read (threats + pawns + summary).")
def combat_triage(ctx):
    cols = _colonists(ctx)
    th = _threats(ctx)
    sm = _summary(ctx)

    hostiles = th.get("hostiles", []) or []
    danger = th.get("danger", "None")
    threat_points = th.get("threat_points", 0)

    # nearest hostile distance
    dists = [h.get("dist_home") for h in hostiles if h.get("dist_home") is not None]
    nearest = min(dists) if dists else None

    colonist_rows = []
    able = 0
    downed = 0
    for c in cols:
        downed_flag = bool(c.get("downed"))
        if downed_flag:
            downed += 1
        else:
            able += 1
        colonist_rows.append({
            "id": c.get("id"), "name": c.get("name"),
            "health": c.get("health"), "downed": downed_flag,
            "bleeding": c.get("bleeding"), "mood": c.get("mood"),
            "weapon": c.get("weapon"), "job": c.get("job"),
            "needs_tending": c.get("needs_tending"),
        })

    # verdict
    if able == 0 and downed > 0:
        verdict = "all_downed"
        rec = ["rescue order should be carrying; check a free bed exists in safe temp"]
    elif able == 1 and hostiles:
        verdict = "last_colonist_under_threat"
        rec = ["do NOT send the last able colonist far from base; hold near home / accept loss"]
    elif hostiles and (nearest is not None and nearest <= 60):
        verdict = "defend"
        rec = ["combat order holds rally; set defend posture; watch for breach"]
    elif downed > 0:
        verdict = "rescue"
        rec = ["rescue order carries downed to bed; ensure a bed in safe temp"]
    else:
        verdict = "safe"
        rec = []

    return {
        "verdict": verdict,
        "danger": danger,
        "threat_points": threat_points,
        "hostile_count": len(hostiles),
        "nearest_hostile_dist": nearest,
        "hostiles": [
            {"id": h.get("id"), "kind": h.get("kind"), "dist": h.get("dist_home"),
             "lord": h.get("lord"), "fogged": h.get("fogged"), "health": h.get("health")}
            for h in hostiles
        ],
        "colonists": colonist_rows,
        "able": able, "downed": downed,
        "recommended": rec,
    }
