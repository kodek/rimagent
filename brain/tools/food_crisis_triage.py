from rimagent.registry import tool


@tool("food_crisis_triage",
      "One-call combined food + mood triage. Replaces the recurring "
      "mood_triage + food_outlook + cook_bill x3 sequence. Returns: "
      "food verdict (days, rice ETA, cooking bills, policy), mood flags "
      "(catharsis crashes, below-threshold pawns), and a single "
      "recommended action list. Run when food_days < 4 or any mood alert.",
      {"radius": "search radius for rice (default 60)"})
def food_crisis_triage(ctx, radius=60):
    # --- food side ---
    s = ctx.bridge.call("state.summary")
    food_days = s.get("food_days")
    head = s.get("colonists") or 0
    ks = s.get("key_stocks") or {}
    meals = ks.get("meals_all", 0)
    meat = ks.get("meat_all", 0)
    survival = ks.get("MealSurvivalPack", 0) or 0

    # food policy
    policy = None
    try:
        pawns = ctx.bridge.call("state.pawns", filter="colonists")
        for p in (pawns or []):
            if p.get("food_policy"):
                policy = p["food_policy"]
                break
    except Exception:
        pass

    # rice harvest ETA
    plants = []
    try:
        raw = ctx.bridge.call("engine.call",
                              path="Map.listerThings.ThingsOfDef", args=["Plant_Rice"])
        plants = raw.get("result", []) if isinstance(raw, dict) else (raw or [])
    except Exception:
        pass
    growths = []
    for p in plants[:30]:
        try:
            g = ctx.bridge.call("engine.get", path=f"Thing:{p.get('id')}.growthInt")
            growths.append(float(g))
        except Exception:
            pass
    avg = (sum(growths) / len(growths)) if growths else 0.0
    harvestable = sum(1 for g in growths if g >= 0.95)
    est_days = round(max(0.0, (1.0 - avg) * 3.0), 1)

    # cooking bills
    bills = []
    for bdef in ("FueledStove", "Campfire"):
        try:
            found = ctx.bridge.call("map.find", kind="building",
                                    **{"def": bdef}, limit=10)
            for st in (found.get("things") or []):
                sid = st.get("id")
                b = ctx.bridge.call("state.bills", thing=sid)
                for bill in (b.get("bills") or []):
                    bills.append({"stove": sid, "recipe": bill.get("recipe"),
                                  "count": bill.get("count"),
                                  "suspended": bill.get("suspended")})
        except Exception:
            pass
    has_cook_bill = any(b.get("recipe") == "CookMealSimple" and not b.get("suspended")
                       for b in bills)

    # --- mood side (catharsis crash check) ---
    mood_flags = []
    try:
        pawns = ctx.bridge.call("state.pawns", filter="colonists")
        for p in (pawns or []):
            name = p.get("name")
            mood = p.get("mood")
            if mood is None:
                continue
            # get catharsis
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
            post_fade = mood - catharsis
            # major threshold ~27% for Losing is Fun
            if mood < 27 or (catharsis > 0 and post_fade < 27):
                mood_flags.append({
                    "name": name,
                    "mood": round(mood, 1),
                    "catharsis": round(catharsis, 1),
                    "post_fade": round(post_fade, 1),
                    "severity": "critical" if mood < 27 else "catharsis_crash",
                })
    except Exception:
        pass

    # --- verdict ---
    actions = []
    if food_days is not None and food_days < 1:
        actions.append(f"EMERGENCY: {food_days}d food for {head} colonists")
    if not has_cook_bill:
        actions.append("NO COOKING BILL: run cook_bill now")
    if est_days <= (food_days or 99) + 0.5 and harvestable > 0:
        actions.append(f"Rice harvestable in {est_days}d ({harvestable} plants) - should self-correct")
    elif food_days is not None and food_days < 4:
        actions.append(f"ADD CAPACITY: rice in {est_days}d but food runs out in {food_days}d - add zone or hunt")
    if survival > 0 and policy and policy.lower() not in ("lavish", "fine", "any", "survival"):
        actions.append(f"POLICY MISMATCH: '{policy}' blocks {survival} survival packs - set to Lavish")
    for f in mood_flags:
        if f["severity"] == "critical":
            actions.append(f"MOOD CRISIS: {f['name']} at {f['mood']}% - run mood_triage")
        else:
            actions.append(f"CATHARSIS CRASH: {f['name']} post-fade {f['post_fade']}% - fix root cause")

    return {
        "day": s.get("day"),
        "food_days": food_days,
        "colonists": head,
        "meals": meals,
        "meat": meat,
        "survival_packs": survival,
        "food_policy": policy,
        "rice": {"plants": len(plants), "avg_growth": round(avg, 3),
                 "harvestable": harvestable, "est_days": est_days},
        "cooking_bills": bills,
        "has_cook_bill": has_cook_bill,
        "mood_flags": mood_flags,
        "actions": actions,
    }
