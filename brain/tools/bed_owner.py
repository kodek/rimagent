from rimagent.registry import tool
@tool("bed_owner", "Assign or clear a bed's owner via engine (bypasses the dialog). action='assign' sets owner; action='clear' removes it. action='list' shows all beds with their current owners.", {"bed": "bed thing id (e.g. Bed93768)", "action": "'assign', 'clear', or 'list' (default 'list')", "pawn": "colonist name to assign as owner (required for action='assign')", "radius": "search radius for action='list' (default 40)"})
def bed_owner(ctx, bed=None, action="list", pawn=None, radius=40):
    """
    Bed owner management via engine.
    
    Engine path for assign: Thing:<bedId>.CompAssignableToPawn.TryAssignPawn
    Engine path for clear:  Thing:<bedId>.CompAssignableToPawn.RemoveAssignedPawns
    
    action='list': find all beds in radius, show owner status.
    action='assign': assign `pawn` to `bed`.
    action='clear': clear the owner of `bed`.
    """
    if action == "list":
        beds = ctx.bridge.call("map.find", kind="building", **{"def": "Bed"}, radius=radius, limit=50)
        result = []
        for b in beds.get("things", []):
            bid = b.get("id")
            owner = None
            try:
                owners = ctx.bridge.call("engine.get", path=f"Thing:{bid}.CompAssignableToPawn.AssignedPawnsForReading", depth=1)
                if owners:
                    owner = [o.get("name") or o.get("LabelShort") or str(o) for o in owners]
            except Exception:
                pass
            result.append({"id": bid, "owner": owner, "pos": b.get("pos")})
        return {"beds": result, "count": len(result)}
    
    if action == "assign":
        if not bed or not pawn:
            return {"error": "action='assign' requires both bed and pawn"}
        try:
            r = ctx.bridge.call(
                "engine.call",
                path=f"Thing:{bed}.CompAssignableToPawn.TryAssignPawn",
                args=[f"Pawn:{pawn}"]
            )
        except Exception as e:
            return {"error": f"Failed to assign: {e}", "bed": bed, "pawn": pawn}
        return {"bed": bed, "pawn": pawn, "result": r}
    
    if action == "clear":
        if not bed:
            return {"error": "action='clear' requires bed"}
        try:
            r = ctx.bridge.call(
                "engine.call",
                path=f"Thing:{bed}.CompAssignableToPawn.RemoveAssignedPawns",
                args=[]
            )
        except Exception as e:
            return {"error": f"Failed to clear: {e}", "bed": bed}
        return {"bed": bed, "cleared": True, "result": r}
    
    return {"error": f"Unknown action: {action}"}
