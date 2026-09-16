from rimagent.registry import tool
@tool(name="destroy_corpses",
      description="Destroy all corpses within a radius (sandbox mode only, uses dev.destroy). One call instead of N rw_dev_destroy calls. Use when desiccated corpses are causing mood drag and cannot be hauled.")
def destroy_corpses(ctx, radius=30):
    result = ctx.bridge.call("map.find", kind="corpse", radius=radius, limit=50)
    things = (result or {}).get("things", [])
    destroyed = []
    failed = []
    for t in things:
        if not isinstance(t, dict):
            continue
        tid = t.get("id")
        if not tid:
            continue
        try:
            ctx.bridge.call("dev.destroy", thing=tid)
            destroyed.append(tid)
        except Exception as e:
            failed.append({"id": tid, "error": str(e)})
    return {
        "destroyed": destroyed,
        "count": len(destroyed),
        "failed": failed,
        "note": "Sandbox mode only (marks game assisted). Desiccated corpses cannot be hauled; destroy them to clear the -6 mood drag."
    }
