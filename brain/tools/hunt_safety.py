from rimagent.registry import tool

@tool(
    name="hunt_safety",
    description="Check all pending Hunt designations: for each, find the target animal's distance from home and whether the species is safe to hunt (0% revenge chance). Returns distances and species safety for all pending hunts.",
    params={"radius": "search radius for animals (default 80)"}
)
def hunt_safety(ctx, radius="80"):
    import json
    r = int(radius)

    # Get home center
    s = ctx.bridge.call("state.summary")
    home = s.get("home_center") or [0, 0]

    # Get pending designations
    desig = ctx.bridge.call("state.designations")
    desigs = desig.get("designations") or []

    # Find all Hunt designations
    hunts = [d for d in desigs if d.get("kind") == "Hunt" or d.get("type") == "Hunt"]

    # Get all animals on map within radius
    animals = ctx.bridge.call("map.find", kind="animal", radius=r, limit=50)
    animal_list = animals.get("things") or []

    # Build a map of animal id -> (distance, def)
    animal_info = {}
    for a in animal_list:
        pos = a.get("pos") or [0, 0]
        dist = ((pos[0] - home[0])**2 + (pos[1] - home[1])**2) ** 0.5
        animal_info[a.get("id")] = {"dist": dist, "def": a.get("def", "")}

    # Safe species: 0% revenge chance
    SAFE_ANIMALS = {"Animal_Hare", "Animal_Squirrel", "Animal_Deer", "Animal_Elk",
                    "Animal_WildBoar", "Animal_Turkey", "Animal_Alpaca", "Animal_Gazelle"}

    # Check each hunt designation
    results = []
    for h in hunts:
        target_id = h.get("thing") or h.get("target") or ""
        info = animal_info.get(target_id)
        if info is None:
            results.append({
                "target": target_id,
                "distance": None,
                "species_safe": None,
                "reason": "target not found on map (may be dead or off-map)"
            })
        else:
            species_safe = info["def"] in SAFE_ANIMALS
            results.append({
                "target": target_id,
                "distance": round(info["dist"], 1),
                "species_safe": species_safe,
                "def": info["def"],
                "reason": "OK" if species_safe else f"UNSAFE SPECIES: {info['def']} (revenge risk)"
            })

    # Find nearest safe animals anywhere on map
    safe_animals = []
    for a in animal_list:
        pos = a.get("pos") or [0, 0]
        dist = ((pos[0] - home[0])**2 + (pos[1] - home[1])**2) ** 0.5
        if a.get("def", "") in SAFE_ANIMALS:
            safe_animals.append({
                "id": a.get("id"),
                "def": a.get("def"),
                "distance": round(dist, 1),
            })
    safe_animals.sort(key=lambda x: x["distance"])

    unsafe_species = [r for r in results if r.get("species_safe") is False]
    return {
        "home": home,
        "total_hunts": len(hunts),
        "hunts": results,
        "unsafe_species": unsafe_species,
        "nearest_safe_animals": safe_animals[:5],
        "verdict": "ALL SAFE" if not unsafe_species else f"{len(unsafe_species)} UNSAFE SPECIES hunt(s) - cancel or wait",
    }
