def watch(ctx, events):
    """On day tick: if food_days < 2 AND no animals within 30 cells of home,
    alert the planner that the colony will starve before the next rice harvest.

    This is the gap that cook_gap and food_crisis_watcher don't cover: the bill
    is running, the rice is growing, but there's a 1.5-day gap between running
    out of food and the harvest landing, and no animals close enough to hunt.
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

        # Check for animals within 30 cells of home
        home = s.get("home_center") or [0, 0]
        try:
            animals = ctx.bridge.call("map.find", kind="animal", radius=30, limit=20)
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
                    "within 30 cells. Rice harvest ETA unknown. Options: (1) send 2 armed "
                    "hunters to the nearest animal 30-60 cells away, (2) forage berries, "
                    "(3) accept starvation risk. Check crop_status for harvest ETA."
                ),
                "wake": True,
            })
    return out
