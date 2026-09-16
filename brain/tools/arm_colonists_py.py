from rimagent.registry import tool


# Ranged weapon defs worth equipping (early game). Melee last resort.
RANGED = ["Gun_BoltAction", "Gun_Revolver", "Gun_Musket", "Gun_Pistol",
          "Gun_Spitter", "Gun_Mortar", "Gun_Automatic", "Gun_ChainShot",
          "Bow_Composite", "Bow_Crossbow", "Bow_Simple", "Bow_Heavy",
          "Turret_MiniTurret", "Turret_Gun"]
MELEE = ["Blade_Short", "Blade_Long", "Blade_Broad", "Blade_Heavy",
         "Blade_Greatsword", "Blade_Dagger", "Blade_Butterfly", "Blade_Machete",
         "Blade_Halberd", "Blade_Hammer", "Blade_Staff", "Blade_Katana"]


@tool("arm_colonists",
      "One-call weapon audit: for each colonist, whether they hold a ranged weapon, "
      "and which loose weapons are on the map near home (ranged first). Returns who "
      "is unarmed and the best weapon to equip on each. action='equip' issues "
      "rw_ui_order equip for the best available weapon per unarmed colonist.",
      {"radius": "search radius for loose weapons from home (default 40)",
       "action": "'report' (default) or 'equip' to arm the unarmed colonists"})
def arm_colonists(ctx, radius=40, action="report"):
    s = ctx.bridge.call("state.summary")
    home = s.get("home_center", [0, 0])
    pawns = ctx.bridge.call("state.pawns", filter="colonists")

    # 1. what each colonist holds
    roster = []
    for p in pawns:
        name = p.get("name")
        equipped = []
        try:
            pd = ctx.bridge.call("state.pawn", pawn=name)
            for g in (pd.get("gear") or []):
                d = (g.get("def") or g.get("label") or "")
                equipped.append(d)
        except Exception:
            pass
        has_ranged = any(any(w in e for w in RANGED) for e in equipped)
        has_any = len(equipped) > 0
        roster.append({"name": name, "equipped": equipped,
                       "has_ranged": has_ranged, "has_any": has_any})

    # 2. loose weapons on the map, ranged first
    weapons = []
    for wdef in RANGED + MELEE:
        try:
            res = ctx.bridge.call("map.find", kind="item", **{"def": wdef},
                                  near=home, radius=radius, limit=50)
            things = res.get("things", []) if isinstance(res, dict) else res
            for t in (things or []):
                if isinstance(t, dict):
                    weapons.append({"id": t.get("id"), "def": wdef,
                                    "pos": t.get("pos"),
                                    "ranged": wdef in RANGED})
        except Exception:
            pass
    weapons.sort(key=lambda w: (not w["ranged"], w.get("def") or ""))

    # 3. match unarmed colonists to the best free weapon
    free = [w for w in weapons]
    assignments = []
    for r in roster:
        if r["has_ranged"]:
            continue
        # pick the best free weapon (ranged first, already sorted)
        pick = free.pop(0) if free else None
        assignments.append({"pawn": r["name"], "weapon": pick["def"] if pick else None,
                            "weapon_id": pick["id"] if pick else None,
                            "note": "unarmed - equip this" if pick else "NO loose weapon found; build/buy one"})

    result = {
        "roster": roster,
        "loose_weapons": weapons,
        "unarmed": [a["pawn"] for a in assignments],
        "assignments": assignments,
    }

    if action == "equip":
        done = []
        for a in assignments:
            if not a["weapon_id"]:
                continue
            try:
                # equip the weapon onto the pawn via right-click order
                ctx.bridge.call("ui.order", pawn=a["pawn"], at=a["weapon_id"],
                                label="equip")
                done.append(a["pawn"])
            except Exception as e:
                a["error"] = str(e)
        result["equipped"] = done
    return result
