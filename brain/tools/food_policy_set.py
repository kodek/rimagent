from rimagent.registry import tool

@tool("food_policy_set",
      "Set the food policy on ALL colonists in one call (collapses N rw_ui_set_policies calls). "
      "Valid labels: Lavish, Fine, Simple, Paste, Raw, Nothing, Vegetarian, Carnivore, Cannibal, Insect meat. "
      "There is NO 'Any' and NO 'Survival' policy. To eat survival packs use Lavish or Fine. "
      "action='list' shows the live policy database + each colonist's current policy.",
      {"action": "set|list (default 'set' if policy given, else 'list')",
       "policy": "policy label to set on every colonist (default 'Lavish')",
       "pawn": "optional: only set this one colonist (name or id)"})
def food_policy_set(ctx, action=None, policy=None, pawn=None):
    # Read the live database so we never hallucinate a label
    db = ctx.bridge.call("engine.get", path="Game.foodRestrictionDatabase.AllFoodRestrictions")
    valid = [p.get("label") for p in db] if isinstance(db, list) else []

    if action is None:
        action = "set" if policy else "list"

    if action == "list":
        pawns = ctx.bridge.call("state.pawns", filter="colonists")
        rows = []
        for p in pawns:
            name = p.get("name") or p.get("id")
            cur = None
            try:
                fr = ctx.bridge.call("engine.get", path=f"Pawn:{name}.foodRestriction.CurrentFoodPolicy")
                cur = fr.get("label") if isinstance(fr, dict) else str(fr)
            except Exception:
                cur = None
            rows.append({"name": name, "current_policy": cur})
        return {"valid_labels": valid, "colonists": rows,
                "note": "No 'Any'/'Survival' policy exists. Survival packs are allowed only by Lavish or Fine."}

    # action == set
    target = policy or "Lavish"
    if valid and target not in valid:
        return {"error": f"'{target}' is not a valid policy label. Valid: {valid}",
                "hint": "To eat survival packs use 'Lavish' or 'Fine'."}

    pawns = ctx.bridge.call("state.pawns", filter="colonists")
    if pawn:
        pawns = [p for p in pawns if (p.get("name") == pawn or p.get("id") == pawn)]

    results = []
    for p in pawns:
        name = p.get("name") or p.get("id")
        try:
            r = ctx.bridge.call("ui.set_policies", pawn=name, food=target)
            ok = not (isinstance(r, dict) and r.get("error"))
            results.append({"pawn": name, "ok": ok, "result": r if not ok else None})
        except Exception as e:
            results.append({"pawn": name, "ok": False, "error": str(e)})

    ok_count = sum(1 for r in results if r.get("ok"))
    return {"set_policy": target, "targeted": len(results), "ok": ok_count,
            "failed": [r for r in results if not r.get("ok")],
            "valid_labels": valid}
