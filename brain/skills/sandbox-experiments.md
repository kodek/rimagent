---
name: sandbox-experiments
description: What to do in a SANDBOX episode (god mode, all research, not scored): a checklist of experiments whose results should become skills, tools and watchers.
tags: [sandbox, experiment, learning, curriculum]
always: false
---
# Sandbox episodes are for learning, not surviving

Blueprints complete instantly and cost nothing; research is done. Every experiment must end with a skill edit, a journal entry, or a tool/watcher. Suggested curriculum; pick what you are weakest at (check score_history and your recent notes):

1. **Power**: build a generator, battery room, coolers, turrets and lamps; wire them with `rw_ui_wire`; read `rw_state_power` and `rw_map_power` until you can predict what they will show. Record consumption numbers and the conduit rules in power-basics.
2. **Freezer**: build one, set coolers to -10C, watch `state.base` room temperature fall; note how long it takes and how many coolers per cell count.
3. **Defense**: build a killbox or chokepoint, then `rw_dev_incident(def="RaidEnemy", points=200)`, watch with `rw_state_threats` at speed 1, draft and position with `rw_ui_goto`. Try 200, 500, 1000 points. Write the defense-basics skill from what actually happened.
4. **Rooms and mood**: build bedrooms of 3x3, 5x5, 7x7 with different furniture; compare `state.base` impressiveness; record the thresholds.
5. **Crops**: sow rice, potatoes, corn side by side; track growth per day with a tool; record days-to-harvest and yield per cell.
6. **Fire**: `rw_dev_incident(def="Flashstorm")` near wood vs stone walls; learn what burns.
7. **Trade and caravans**: call a trader (`rw_dev_incident(def="TraderCaravanArrival")`), open the trade dialog through `rw_state_dialogs`, buy and sell, and record prices.
8. **Anything that killed you last time**: reproduce it and find the counter.
Keep a running list of results in the notebook, then fold them into skills before the sandbox ends (it ends after `sandbox_days`).
