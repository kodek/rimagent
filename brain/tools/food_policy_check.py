from rimagent.registry import tool

# Correct policy allow-sets, verified from FoodRestrictionDatabase.cs (RimWorld 1.6):
#   Lavish: allows ALL food (no blocks)
#   Fine:   blocks preferability>=10 -> allows survival packs(9), simple meals(9), raw; blocks fine meals, nutrient paste
#   Simple: blocks preferability>=9 AND explicitly disallows MealSurvivalPack -> allows raw only
#   Paste:  allows only nutrient paste
#   Raw:    blocks preferability>=7 -> allows raw food only
#   Nothing: allows nothing
# There is NO "Any" and NO "Survival" policy. Survival packs are edible only under Lavish or Fine.
ALLOW = {
    "Lavish":   {"survival", "simple", "fine", "paste", "raw"},
    "Fine":     {"survival", "simple", "raw"},
    "Simple":   {"raw"},
    "Paste":    {"paste"},
    "Raw":      {"raw"},
    "Nothing":  set(),
}
# A policy with an unknown/renamed label: assume it allows raw + survival + simple (safe default, flag it)
DEFAULT_ALLOW = {"survival", "simple", "raw"}

def _cat(defname):
    d = defname.lower()
    if "survival" in d:
        return "survival"
    if "nutrientpaste" in d or "nutrient" in d:
        return "paste"
    if "meal" in d:
        # MealFine vs MealSimple
        return "fine" if "fine" in d else "simple"
    return "raw"  # rice, potato, corn, meat, berries, egg, milk, etc.

@tool("food_policy_check",
      "Check whether each colonist's food policy allows the food actually in stock. "
      "Policies are a live DB (Lavish/Fine/Simple/Paste/Raw/Nothing, +ideology) - there is NO 'Any'/'Survival'. "
      "Survival packs are edible only under Lavish or Fine. Returns per-colonist match + recommended fix.",
      {"radius": "unused"})
def food_policy_check(ctx, radius=None):
    summary = ctx.bridge.call("state.summary")
    pawns = ctx.bridge.call("state.pawns", filter="colonists")

    # food defs in stock (stored + outside)
    food_items = []
    for src in ("key_stocks", "outside_storage"):
        for k, v in (summary.get(src) or {}).items():
            if isinstance(v, int) and v > 0:
                if any(x in k.lower() for x in ["meal", "rice", "potato", "corn", "meat", "berry",
                                                 "survival", "egg", "milk", "nutrient", "food", "chocolate"]):
                    food_items.append(k)
    cats_present = sorted({_cat(f) for f in food_items})

    # recommended policy that covers everything in stock
    rec = None
    for pol, allow in ALLOW.items():
        if pol == "Nothing":
            continue
        if set(cats_present) <= allow:
            rec = pol
            break
    if rec is None:
        rec = "Lavish"  # always covers everything

    # per-colonist check
    rows = []
    for p in pawns:
        name = p.get("name") or p.get("id")
        pol = p.get("food_policy")
        pol_key = pol if pol in ALLOW else None
        allow = ALLOW.get(pol, DEFAULT_ALLOW)
        blocked = [c for c in cats_present if c not in allow]
        rows.append({"name": name, "policy": pol,
                    "unknown_policy": pol_key is None,
                    "blocked_categories": blocked,
                    "ok": not blocked and pol_key is not None})

    bad = [r for r in rows if not r["ok"]]
    return {
        "food_categories_in_stock": cats_present,
        "recommended_policy": rec,
        "colonists": rows,
        "mismatched": bad,
        "note": "No 'Any'/'Survival' policy exists. Survival packs need Lavish or Fine.",
    }
