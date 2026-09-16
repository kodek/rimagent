from rimagent.registry import tool

@tool("set_bill",
      "Set a bill on a station (butcher, research, drug lab, etc.). "
      "Checks for existing bills first to avoid duplicates. "
      "One call instead of 2-3 rw_ui_bill calls. "
      "Returns the station id, bill index, and whether it was already running.",
      {"station": "station thing id (e.g. ButcherTable1234, ResearchBench5678)",
       "recipe": "recipe defName (e.g. ButcherCorpseFlesh, ResearchProject, MakeMedicineHerbal)",
       "mode": "bill mode: Forever (default), TargetCount, or Once",
       "count": "count for TargetCount mode (default 10)"})
def set_bill(ctx, station, recipe, mode="Forever", count=10):
    # Check existing bills on this station
    try:
        bills = ctx.bridge.call("state.bills", thing=station)
        existing = bills.get("bills") or []
    except Exception:
        existing = []

    # Check if this recipe is already running
    for b in existing:
        if b.get("recipe") == recipe and not b.get("suspended"):
            return {
                "station": station,
                "recipe": recipe,
                "already_running": True,
                "bill_index": b.get("index"),
                "count": b.get("count"),
                "note": f"{recipe} already running on {station}."
            }

    # Add the bill
    try:
        if mode == "Forever":
            result = ctx.bridge.call("ui.add_bill",
                                     thing=station,
                                     recipe=recipe,
                                     mode="TargetCount",
                                     count=999)
        elif mode == "Once":
            result = ctx.bridge.call("ui.add_bill",
                                     thing=station,
                                     recipe=recipe,
                                     mode="Once")
        else:
            result = ctx.bridge.call("ui.add_bill",
                                     thing=station,
                                     recipe=recipe,
                                     mode="TargetCount",
                                     count=count)
    except Exception as e:
        return {"error": f"Failed to add bill: {e}", "station": station, "recipe": recipe}

    return {
        "station": station,
        "recipe": recipe,
        "mode": mode,
        "count": count if mode == "TargetCount" else None,
        "result": result,
        "note": f"{recipe} bill set on {station}."
    }
