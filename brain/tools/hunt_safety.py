from rimagent.registry import tool
@tool(
    name="hunt_safety",
    description="Check all pending Hunt designations: for each, find the target animal's distance from home and flag if >30 cells (unsafe). Returns list of unsafe hunts with distances and the nearest safe animal.",
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
    
    # Build a map of animal id -> distance
    animal_dists = {}
    for a in animal_list:
        pos = a.get("pos") or [0, 0]
        dist = ((pos[0] - home[0])**2 + (pos[1] - home[1])**2) ** 0.5
        animal_dists[a.get("id")] = dist
    
    # Check each hunt designation
    results = []
    for h in hunts:
        target_id = h.get("thing") or h.get("target") or ""
        # Try to match by thing id
        dist = animal_dists.get(target_id)
        if dist is None:
            # Target might be off-map or already dead
            results.append({
                "target": target_id,
                "distance": None,
                "safe": False,
                "reason": "target not found on map (may be dead or off-map)"
            })
        else:
            safe = dist <= 30
            results.append({
                "target": target_id,
                "distance": round(dist, 1),
                "safe": safe,
                "reason": "OK" if safe else f"TOO FAR ({dist:.0f} cells > 30)"
            })
    
    # Find nearest safe animal (0% revenge preferred)
    SAFE_ANIMALS = {"Plant_Hare", "Animal_Hare", "Plant_Squirrel", "Animal_Squirrel",
                    "Animal_Deer", "Animal_Elk", "Animal_WildBoar", "Animal_Turkey",
                    "Animal_Alpaca", "Animal_Gazelle"}
    safe_animals = []
    for a in animal_list:
        pos = a.get("pos") or [0, 0]
        dist = ((pos[0] - home[0])**2 + (pos[1] - home[1])**2) ** 0.5
        if dist <= 30:
            safe_animals.append({
                "id": a.get("id"),
                "def": a.get("def"),
                "distance": round(dist, 1),
                "safe_species": a.get("def", "") in SAFE_ANIMALS
            })
    safe_animals.sort(key=lambda x: x["distance"])
    
    unsafe = [r for r in results if not r["safe"]]
    return {
        "home": home,
        "total_hunts": len(hunts),
        "unsafe_hunts": unsafe,
        "safe_animals_within_30": safe_animals[:5],
        "verdict": "ALL SAFE" if not unsafe else f"{len(unsafe)} UNSAFE hunt(s) - cancel or wait",
    }
