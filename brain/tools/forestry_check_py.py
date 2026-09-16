from rimagent.registry import tool


@tool("forestry_check",
      "Diagnose a stalled forestry job: current/target, designations, failures, and "
      "how many trees actually exist within the default radius vs an extended radius. "
      "Run when the Steward block shows forestry 'no valid trees' or wood is dropping "
      "and the job is not cutting. Tells you whether to raise max_radius, lower the "
      "target, or plant trees.",
      {"radius": "default search radius for trees (default 70, the job's MaxWorkRadius)",
       "wide": "extended radius to look for trees beyond the default (default 120)"})
def forestry_check(ctx, radius=70, wide=120):
    s = ctx.bridge.call("state.summary")
    home = s.get("home_center", [0, 0])
    ks = s.get("key_stocks") or {}
    wood = ks.get("WoodLog", 0)

    # steward stock row for forestry
    row = None
    try:
        status = ctx.bridge.call("steward.status")
        for j in (status.get("stock") or []):
            if j.get("kind") == "forestry" or j.get("id") in ("forestry",):
                row = j
                break
        if row is None:
            for j in (status.get("stock") or []):
                if "forest" in (j.get("label") or "").lower() or "wood" in (j.get("label") or "").lower():
                    row = j
                    break
    except Exception:
        row = None

    # trees within default and wide radius
    def _trees(r):
        try:
            res = ctx.bridge.call("map.find", kind="tree", near=home, radius=r, limit=400)
            things = res.get("things", []) if isinstance(res, dict) else res
            return [t for t in (things or []) if isinstance(t, dict)]
        except Exception:
            return []

    near = _trees(radius)
    wide_trees = _trees(wide)
    # how many are beyond the default radius (i.e. only reachable by raising max_radius)
    beyond = [t for t in wide_trees if t not in near]

    problems = []
    if row is None:
        problems.append("no forestry job found in steward status (stock disabled?) - run rw_steward_enable(stock=true)")
    else:
        cur = row.get("current")
        tgt = row.get("target")
        desig = row.get("designations")
        fails = row.get("failures")
        if tgt and cur is not None and cur >= tgt:
            problems.append(f"target met ({cur}/{tgt}) - job correctly idle; lower the target to keep cutting")
        elif desig in (0, None) and (fails or row.get("summary", "").lower().find("no valid") >= 0):
            problems.append(f"no valid trees within radius {radius} - {len(beyond)} trees exist out to {wide}; "
                            f"raise max_radius or lower the target")
        elif cur is not None and tgt and cur < tgt and desig:
            problems.append(f"cutting normally ({cur}/{tgt}, {desig} designated)")

    return {
        "wood_in_storage": wood,
        "job": {k: row.get(k) for k in ("current", "target", "designations", "failures",
                                         "enabled", "suspended", "last_run_hours_ago", "summary")} if row else None,
        "trees_within_default": len(near),
        "trees_within_wide": len(wide_trees),
        "trees_beyond_default": len(beyond),
        "problems": problems,
    }
