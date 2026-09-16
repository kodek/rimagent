from rimagent.registry import tool
@tool("ideo_role", "List or assign ideo roles for a colonist. action='list' shows available roles; action='assign' assigns by role name (case-insensitive substring match).", {"pawn": "colonist name or id", "action": "'list' or 'assign' (default 'list')", "role": "role name to assign (e.g. 'Moralist', 'Fidelist', 'Uplifter')", "force": "pass True to force-assign even if the pawn already has a role"})
def ideo_role(ctx, pawn, action="list", role=None, force=False):
    """
    ideo role assignment via engine.
    
    Path: Pawn:<name>.ideo.ideo.cachedPossibleRoles is a list of RoleDef-like objects.
    Each has .defName (e.g. 'Moralist') and .Assign(pawn, force) method.
    
    action='list': returns all available roles with their defNames and whether assigned.
    action='assign': assigns the role matching `role` (substring, case-insensitive).
    """
    # Get the pawn's ideo component
    try:
        ideo = ctx.bridge.call("engine.get", path=f"Pawn:{pawn}.ideo.ideo")
    except Exception as e:
        return {"error": f"Could not access ideo component: {e}"}
    
    if ideo is None:
        return {"error": "Pawn has no ideo component (no ideo mod loaded or pawn is AI)"}
    
    # Get cached possible roles
    try:
        roles = ctx.bridge.call("engine.get", path=f"Pawn:{pawn}.ideo.ideo.cachedPossibleRoles", depth=2)
    except Exception as e:
        return {"error": f"Could not read cachedPossibleRoles: {e}"}
    
    if not roles:
        return {"error": "No cached possible roles (ideo not initialised yet?)"}
    
    # Build role list
    role_list = []
    for i, r in enumerate(roles):
        if isinstance(r, dict):
            role_list.append({
                "index": i,
                "defName": r.get("defName") or r.get("def_name") or str(r.get("def", "")),
                "label": r.get("label") or r.get("defName"),
            })
        else:
            role_list.append({"index": i, "defName": str(r)})
    
    if action == "list":
        return {"pawn": pawn, "roles": role_list}
    
    if action == "assign":
        if not role:
            return {"error": "action='assign' requires the role parameter"}
        role_lower = role.lower()
        target = None
        for i, r in enumerate(roles):
            if isinstance(r, dict):
                name = (r.get("defName") or r.get("label") or "").lower()
            else:
                name = str(r).lower()
            if role_lower in name:
                target = i
                break
        if target is None:
            return {"error": f"Role '{role}' not found. Available: {[r.get('defName') or r for r in roles]}"}
        
        # Assign via engine_call
        try:
            result = ctx.bridge.call(
                "engine.call",
                path=f"Pawn:{pawn}.ideo.ideo.cachedPossibleRoles[{target}]",
                args=[f"Pawn:{pawn}", bool(force)]
            )
        except Exception as e:
            return {"error": f"Assign failed: {e}", "role_index": target}
        
        return {"pawn": pawn, "assigned": role, "index": target, "result": result}
