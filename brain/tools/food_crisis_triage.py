"""Combined food + mood triage in one call. Returns food days, food breakdown,
rice ETA, running cook bills, per-colonist food-policy vs stock, mood flags, and a
recommended action list. Use INSTEAD of the 3-call sequence
(mood_triage + food_outlook + cook_bill).

The #1 repeated failure is the survival-pack starvation trap: the only food is
survival packs but a colonist's policy is Simple/Paste/Raw/Nothing, so they will
not eat them and starve while packs sit in the stockpile. This tool detects it.
"""
import json

def _map_find(ctx, thing_def):
    # 'def' is a Python reserved word; pass via dict unpacking
    return ctx.bridge.call("map.find", **{"def": thing_def})

def _food_policy(ctx, pawn_id):
    try:
        return ctx.bridge.call("engine.get",
            path=f"Pawn:{pawn_id}.foodRestriction.CurrentFoodPolicy.label")
    except Exception:
        return None

def _rice_eta(ctx):
    try:
        r = _map_find(ctx, "Plant_Rice")
    except Exception:
        return None
    things = r.get("things", []) if isinstance(r, dict) else []
    if not things:
        return None
    best = max(t.get("growth", 0.0) for t in things)
    n = len(things)
    days_left = round((1.0 - best) * 3.0, 2)  # rice grow_days = 3
    return {"plants": n, "best_growth": best, "harvestable": best >= 1.0,
            "days_to_harvest": days_left}

def _cook_bills(ctx):
    bills = []
    for station_def in ("FueledStove", "Campfire", "ElectricStove"):
        try:
            f = _map_find(ctx, station_def)
        except Exception:
            continue
        for t in (f.get("things", []) if isinstance(f, dict) else []):
            try:
                b = ctx.bridge.call("state.bills", thing=t["id"])
            except Exception:
                continue
            for bill in (b if isinstance(b, list) else []):
                if bill.get("recipe") in ("CookMealSimple", "CookMealFine", "CookMealLavish"):
                    bills.append({"station": t["id"], "station_def": station_def,
                                  "recipe": bill.get("recipe"),
                                  "suspended": bill.get("suspended"),
                                  "mode": bill.get("mode"), "target": bill.get("target")})
    return bills

# which policies allow which food category
POLICY_ALLOWS = {
    "MealSurvivalPack": {"Lavish", "Fine"},
    "MealSimple":       {"Lavish", "Fine", "Simple", "Paste"},
    "MealFine":         {"Lavish", "Fine"},
    "NutrientPaste":    {"Lavish", "Fine", "Paste"},
    "RawFood":          {"Lavish", "Fine", "Simple", "Raw"},
}

def food_crisis_triage(ctx):
    s = ctx.bridge.call("state.summary")
    food_days = s.get("food_days")
    nutrition = s.get("nutrition")
    ks = s.get("key_stocks", {})

    # food breakdown (stored)
    try:
        fs = ctx.bridge.call("state.stocks", category="Foods")
        counted = fs.get("counted", {}) if isinstance(fs, dict) else {}
    except Exception:
        counted = {}

    rice = _rice_eta(ctx)
    bills = _cook_bills(ctx)
    active_cook = [b for b in bills if not b.get("suspended")]

    # per-colonist food policy
    colonists = s.get("colonist_list", [])
    policies = []
    for c in colonists:
        lab = _food_policy(ctx, c["id"])
        policies.append({"id": c["id"], "name": c.get("name"), "policy": lab,
                         "mood": c.get("mood"), "health": c.get("health")})

    # which food categories are actually in stock
    stock_cats = set()
    if counted.get("MealSurvivalPack"): stock_cats.add("MealSurvivalPack")
    if counted.get("MealSimple") or counted.get("meals_all"): stock_cats.add("MealSimple")
    if counted.get("MealFine"): stock_cats.add("MealFine")
    if counted.get("NutrientPaste"): stock_cats.add("NutrientPaste")
    raw_keys = [k for k in counted if k.startswith("Raw")]
    if raw_keys or counted.get("meat_all"): stock_cats.add("RawFood")

    # policy-vs-stock mismatches (the starvation trap)
    mismatches = []
    for p in policies:
        lab = p["policy"]
        for cat in stock_cats:
            if cat in POLICY_ALLOWS and lab not in POLICY_ALLOWS[cat]:
                mismatches.append({"pawn": p["name"], "policy": lab,
                                   "blocked_food": cat})

    # mood flags
    mood_flags = []
    for c in colonists:
        m = c.get("mood")
        if m is not None and m < 40:
            mood_flags.append({"name": c.get("name"), "mood": m,
                               "level": "break-risk" if m < 20 else "low"})

    # recommended actions
    actions = []
    if not active_cook and food_days is not None and food_days < 6:
        actions.append("no active cook bill and food_days<6: run cook_bill now")
    if mismatches:
        cats = sorted({m["blocked_food"] for m in mismatches})
        rec = "Lavish" if "MealSurvivalPack" in cats else "Fine"
        actions.append(f"food policy blocks {cats} for {len(mismatches)} colonist(s): "
                       f"food_policy_set(policy={rec})")
    if food_days is not None and food_days < 3:
        actions.append("FOOD EMERGENCY: food_days<3")
    if rice and rice.get("harvestable") and not active_cook:
        actions.append("rice ready but no cook bill: harvest + cook now")

    return {
        "food_days": food_days, "nutrition": nutrition,
        "food_stored": counted, "key_stocks": ks,
        "rice": rice, "cook_bills": bills, "active_cook_bills": active_cook,
        "policies": policies, "stock_categories": sorted(stock_cats),
        "policy_mismatches": mismatches, "mood_flags": mood_flags,
        "mood_avg": s.get("mood_avg"),
        "actions": actions,
    }
