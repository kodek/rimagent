def watch(ctx, events):
    """On day tick: if food_days < 2 AND no meat-bearing animals on the map,
    alert the planner that the colony will starve before the next rice harvest.

    This is the gap that cook_gap and food_crisis_watcher don't cover: the bill
    is running, the rice is growing, but there's a 1.5-day gap between running
    out of food and the harvest landing, and no animals to hunt.
    """
    out = []
    for ev in events:
        if ev.get("kind") != "day":
            continue
        try:
            s = ctx.bridge.call("state.summary")
        except Exception:
            continue

        food_days = s.get("food_days")
        if food_days is None or food_days >= 2:
            continue

        # Check for meat-bearing animals anywhere on the map
        try:
            animals = ctx.bridge.call("map.find", kind="animal", radius=80, limit=50)
        except Exception:
            animals = {"things": []}

        animal_list = animals.get("things") or []
        # Filter to meat-bearing animals (exclude predators, rats, squirrels)
        MEAT_ANIMALS = {"Animal_Hare", "Animal_Deer", "Animal_Elk", "Animal_WildBoar",
                        "Animal_Turkey", "Animal_Alpaca", "Animal_Muffalo", "Animal_Gazelle"}
        safe_meat = [a for a in animal_list if a.get("def") in MEAT_ANIMALS]

        if not safe_meat:
            out.append({
                "type": "alert",
                "text": (
                    f"STARVATION GAP: food_days={food_days:.1f}, no meat-bearing animals "
                    "on the map. Rice harvest ETA unknown. Options: (1) forage berries, "
                    "(2) accept starvation risk. Check crop_status for harvest ETA."
                ),
                "wake": True,
            })
    return out
