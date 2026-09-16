from rimagent.registry import tool

@tool("position_shooters",
      "One-call: issue rw_ui_goto for every drafted colonist to a target cell. "
      "Collapses N rw_ui_goto calls into one. Pass the chokepoint cell from the "
      "notebook. If cell is omitted, uses the home center. Returns the list of "
      "pawns positioned and any failures.",
      {"cell": "target [x,z] to send all drafted colonists to (default: home center)",
       "radius": "search radius for drafted colonists (default 80)"})
def position_shooters(ctx, cell=None, radius=80):
    # Get drafted colonists
    try:
        pawns = ctx.bridge.call("state.pawns", filter="colonists")
    except Exception as e:
        return {"error": f"Failed to read pawns: {e}"}

    drafted = [p for p in pawns if p.get("drafted")]
    if not drafted:
        return {"error": "No drafted colonists found. Draft them first (hostile_draft watcher or rw_ui_draft)."}

    # Resolve target cell
    if cell is None:
        try:
            s = ctx.bridge.call("state.summary")
            cell = s.get("home_center")
        except Exception:
            cell = None
    if cell is None:
        return {"error": "No target cell and no home_center available."}

    results = []
    for p in drafted:
        name = p.get("name", p.get("id", "?"))
        try:
            r = ctx.bridge.call("ui.goto", pawn=name, cell=cell)
            results.append({"pawn": name, "ok": True, "result": r})
        except Exception as e:
            results.append({"pawn": name, "ok": False, "error": str(e)})

    ok = sum(1 for r in results if r["ok"])
    return {
        "target_cell": cell,
        "positioned": ok,
        "failed": len(results) - ok,
        "details": results,
        "note": f"Positioned {ok}/{len(results)} drafted colonists at {cell}. "
                "Set game speed to 1 for precise combat."
    }
