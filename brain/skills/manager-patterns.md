---
name: manager-patterns
description: Two automation patterns worth owning as your own watchers and tools: threshold stock management (the "colony manager" pattern: keep 300 wood, 200 meat, 100 steel by designating work when stock falls below) and a skill-weighted work priority matrix (the "free will" pattern). Pull in when you keep re-doing resource or priority chores by hand.
tags: [automation, watcher, stock, work-priorities, colony-manager, free-will]
always: false
---
# Pattern 1: threshold stock management (colony manager)

Players keep a table: resource -> target -> how to get more. A watcher can do this every poll without you:

```python
# brain/watchers/stock_targets.py
TARGETS = {"WoodLog": (300, "trees"), "MeatRaw": (150, "hunt"), "Steel": (150, "mine_steel")}
_last_check = {"day": -1}

def watch(ctx, events):
    days = [e for e in events if e.get("kind") == "day"]
    if not days:
        return []            # once per day is plenty
    out = []
    s = ctx.bridge.call("state.summary")
    stocks = s.get("key_stocks", {})
    home = s.get("home_center")
    if stocks.get("WoodLog", 0) < TARGETS["WoodLog"][0]:
        trees = ctx.bridge.call("map.find", kind="tree", near=home, radius=35, limit=12)["things"]
        ids = [t["id"] for t in trees if not t.get("forbidden")]
        if ids:
            out.append({"type": "action", "method": "ui.designate", "params": {"designator": "harvestwood", "things": ids}, "note": f"wood {stocks.get('WoodLog',0)} < 300: cutting {len(ids)} trees"})
    if s.get("meat_all", 0) < TARGETS["MeatRaw"][0]:
        animals = ctx.bridge.call("map.find", kind="animal", near=home, radius=40, limit=6)["things"]
        safe = [a for a in animals if a.get("kind") in ("Deer", "Elk", "Muffalo", "Alpaca", "Hare", "Squirrel", "Turkey", "Ibex", "Gazelle")]
        if safe:
            out.append({"type": "action", "method": "ui.designate", "params": {"designator": "hunt", "things": [safe[0]["id"]]}, "note": "meat low: hunting one safe animal"})
    return out
```
Rules that make it safe: check once per day (on the `day` event), designate a bounded batch, never hunt predators or revenge animals (boomalope, elephant, thrumbo, bears, warg), and read `state.stocks` first so you do not over-designate. Extend with mining: `map.find(kind="resource_rock")` then `ui.designate(designator="mine", things=[...])`.

# Pattern 2: skill-weighted priority matrix (free will)

Priorities 1..4 where 1 is done first; 0 is off. A good default for 3-6 colonists:
- Firefighter 1, Patient 1, Doctor 1 (best Medicine only; others 3), PatientBedRest 1, BasicWorker 1 for everyone.
- Cooking 1 for the best cook only (Cooking >= 6 avoids food poisoning), 0 for pawns with Cooking < 4.
- Growing 1 for Plants >= 8, 2 for 4-7.
- Construction 1 for Construction >= 8 (or the highest), 2 for the rest who can.
- Hunting 1 for the best Shooting with a ranged weapon, 0 for everyone else.
- Mining 2 for Mining >= 6. Crafting/Smithing/Tailoring 2 for the relevant skill >= 6.
- Hauling 3 and Cleaning 3 for everyone; 2 for pawns with no good skills.
- Research 1 for the best Intellectual, 4 for others.
- Warden 2 for the best Social. Handling 2 for Animals >= 6.
Passions (`!` minor, `!!` major) learn faster: prefer a passionate 6 over an indifferent 8 for long-term jobs.

Implement it once as a tool: read `rw_state_work_matrix`, compute the matrix from skills/passions/disabled flags, apply with `rw_ui_set_work_many`. Re-run when a colonist joins or leaves, and after major injuries. Log what changed in the notebook.
