def watch(ctx, events):
    """On day tick: check if ANY colonist's food policy excludes the food actually in stock.

    CORRECTED policy model (verified from FoodRestrictionDatabase.cs, RimWorld 1.6):
    Food policies are a live database, NOT a fixed enum. Valid labels:
        Lavish, Fine, Simple, Paste, Raw, Nothing (+ Vegetarian/Carnivore/Cannibal/Insect meat).
    There is NO 'Any' and NO 'Survival' policy.
    Survival packs (preferability 9) are allowed ONLY by Lavish and Fine:
        Lavish -> all food
        Fine   -> survival, simple meals, raw   (blocks fine meals, nutrient paste)
        Simple -> raw only                     (explicitly disallows survival packs)
        Paste  -> nutrient paste only
        Raw    -> raw only
        Nothing-> nothing
    So if the only food is survival packs, the fix is to set the policy to 'Lavish' or 'Fine',
    NOT 'Any'/'Survival' (those don't exist and the set call will error).
    """
    out = []
    for ev in events:
        if ev.get("kind") != "day":
            continue
        try:
            s = ctx.bridge.call("state.summary")
        except Exception:
            continue

        try:
            pawns = ctx.bridge.call("state.pawns", filter="colonists")
        except Exception:
            pawns = []

        ks = s.get("key_stocks", {})
        survival = ks.get("MealSurvivalPack", 0) or 0
        meals = ks.get("meals_all", 0) or ks.get("MealSimple", 0) or 0
        raw = ks.get("raw_food", 0) or ks.get("rice", 0) or 0

        has_survival = survival > 0
        has_meals = meals > 0
        has_raw = raw > 0

        # Policies that EXCLUDE survival packs: Simple, Paste, Raw, Nothing
        # Policies that ALLOW survival packs: Lavish, Fine
        excludes_survival = {"simple", "paste", "raw", "nothing"}

        blocked = []
        for p in pawns:
            policy = p.get("food_policy")
            if not policy:
                # null policy -> DefaultFoodRestriction() = Lavish (the first DB entry) -> allows survival
                continue
            pl = policy.lower()
            if pl in excludes_survival and has_survival:
                blocked.append((p.get("name", "?"), policy, survival))

        if blocked:
            names = ", ".join(f"{n} ({pol})" for n, pol, _ in blocked)
            out.append({
                "type": "alert",
                "text": (
                    f"FOOD POLICY MISMATCH: {names} will NOT eat survival packs "
                    f"({survival} in stock). Set their policy to 'Lavish' or 'Fine' "
                    f"(there is no 'Any'/'Survival' policy). food_days={s.get('food_days', '?')}."
                ),
                "wake": True,
            })

        if not has_survival and not has_meals and not has_raw and s.get("food_days", 99) < 3:
            out.append({
                "type": "alert",
                "text": (
                    f"NO FOOD IN STOCK: food_days={s.get('food_days', '?')}, "
                    "no meals, raw food, or survival packs. Check rice harvest ETA "
                    "and queue cooking bills immediately."
                ),
                "wake": True,
            })
    return out
