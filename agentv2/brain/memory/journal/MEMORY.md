# Journal, lessons that survive between games


## 2026-09-16 18:51 (episode 1): ui.build needs explicit stuff
RimBridge build calls: ui.build and ui.build_many require an explicit `stuff` for any stuff-made def (Wall, Door, Bed, table, stool). Omitting it does NOT auto-pick a material — it returns the list of legal stuffs and places nothing, a silent no-op that looks like a failed build. Always pass stuff="WoodLog"/"BlocksGranite". Batch whole layouts (wall rect outline + door cell + furniture) into one ui.build_many call; the door op replaces the wall cell inside the same batch. Pending-blueprint counts grouped by def are the fastest way to see a stuck build.

## 2026-09-16 18:51 (episode 1): Steward buries everything under Hauling 1
Steward-managed colony artifact: when loose items lie around (e.g. right after landing), the steward scorer puts Hauling 1 on every pawn and Cooking/Construction/Research starve. Symptom: 0 meals while raw food sits in the stockpile, or a blueprint count frozen for a day. Diagnose in this order: (1) does the stove/campfire actually have a CookMealSimple bill, (2) is any pawn's Cooking > 0, (3) then bias away the Hauling with steward.posture(work={"Hauling":-0.5,"Cooking":0.5}) rather than hand-editing priorities (hand-editing ejects the pawn from steward management).

## 2026-09-16 18:56 (episode 1): "placed" blueprints != built/enclosed room
ui.build / ui.build_many / room() returning `placed` with no `failed` only means blueprints were placed — not that walls are built or the room is enclosed. A single Door left as an unbuilt frame keeps the whole room "outdoors" (beds read as outside -> pawns log "slept outside/on the ground/in the cold", ~-12 mood) even while the game cheerfully reports no build errors. Verify enclosure from STATE: state.summary.room_digest must show a Barracks/Bedroom row with indoor temp, and .blueprints and .frames must be 0. Do not trust the build result; do not hand-designate the missing wall/door, just raise a Construction posture until frames==0.

## 2026-09-16 19:09 (episode 1): New work table needs its bill (verified recipe defNames)
A production table with no bill looks idle exactly like a work-priority bug — always add the bill after it is built. Verified RimWorld 1.6 recipe defNames: FueledStove/ElectricStove + Campfire -> CookMealSimple (TargetCount); ButcherSpot -> ButcherCorpseFlesh (Forever); TableStonecutter -> Make_StoneBlocksAny (Forever); TableSculpting -> Make_SculptureSmall/Make_SculptureLarge (TargetCount). Fine/Lavish meals and Pemmican are "(locked)" until their research. `ui.add_bill` does NOT dedupe — calling it twice stacks two identical bills (I stacked a double butcher bill). Add bills through an idempotent helper (my tools production_status / ensure_bills) rather than by hand. Bills live on the built table's id, from map.find(kind=building, def=...).

## 2026-09-16 19:09 (episode 1): Python tool: `def` is a keyword — pass bridge params via **{"def": ...}
Writing brain tools py: bridge methods that take a param literally named `def` (defs.get, map.find, ui.build for floors) cannot be called as rpc("defs.get", def=x) — that is a Python SyntaxError ("def" is a reserved word), which shows up as "SyntaxError: invalid syntax" in run_python. Use rpc("defs.get", **{"def": x}) or ctx.bridge.call("map.find", **{"def": "Wall"}). Cost me a wasted call.

## 2026-09-16 19:27 (episode 1): Trap adjacency makes a dead blueprint, not an error
Spike traps cannot be adjacent to another trap. The consequence is nastier than it sounds: if you place a trap blueprint diagonally/orthogonally next to an already-built trap, it simply NEVER fills — no error, no build icon change, just a blueprint count that stays put forever and looks exactly like "no builder / no material". I lost several steps to one stray Blueprint_TrapSpike. Rule: after placing traps, list pending blueprints and CANCEL any trap blueprint that sits next to an existing trap; keep a lane's other column as fence/wall instead.

## 2026-09-16 19:27 (episode 1): Steward stock-job targets are ceilings in units; lower them to release a pawn
The steward's stock jobs (forestry/foraging/hunting/mining/livestock) keep designating toward a numeric target. A hunting target is counted in meat units, so a big default (e.g. 525) makes the designated hunter hunt forever and starve every other job — especially when the hunter is also your only builder. Lower or raise the target instead of hand-designating animals: rw_steward_stock_set(kind=hunting, target=120) released my builder within a day. The Stock block shows `target (current)` per job, and `rw_steward_stock_run(kind=...)` forces a pass now. Never hand-designate animals/trees/ore while the matching stock job is enabled — raise or lower its target, or the job just re-designates.

## 2026-09-16 (episode 2): Steward scorer can zero a pawn's whole work matrix; fix = full manual matrix
Symptom: state.work_matrix shows a managed pawn with nearly all work types 0 (mine: only Patient 1, Doctor 3, PatientBedRest 1, Firefighter "X"), while another pawn looks sane and a third is mid-write. Appears after a posture re-issue + combat-order release. `steward.pawn(managed=true)` re-hand-back only partially helps (re-scored 1 of 3 pawns). Fix that worked: rw_ui_set_work with an explicit 0-4 matrix over ALL 23 work types, per pawn.
COST (from the tool's own note): unmanaged pawns are SKIPPED by the combat standing order — no auto-draft in raids. With all 3 pawns manual, on hostile_group you must rw_ui_draft the armed pawns yourself and push them to the rally rect.
Also: a row where a Major-passion skill work (Intel 5) reads Research 0 despite an in-progress project + posture +0.5 is under-output; cross-check the matrix against colony needs (research in progress => someone at Research 1-3) before trusting it.

## 2026-09-16 22:00 (episode 4): Tree growth threshold blocks steward forestry
Steward forestry job with `allow_saplings=False` (the default) only designates trees with growth >= 1.0. In early game, poplars (15-day grow) are often at 0.4-0.98 growth, so the job stalls with "no valid trees (count N / target 500)" while 10+ trees sit right there. Fix: `rw_steward_stock_set(kind="forestry", target=500, allow_saplings=True)` or wait ~5-10 days for trees to reach 1.0. A tree at 0.98 growth still yields ~98% of its full wood. Also: the "no designation needed" / "not haulable" error when manually designating cut on a tree means the tree is too young (growth < ~0.5) or the cell is in a growing zone.

## 2026-09-16 (episode 4, day 8): allow_saplings fix tool absent in this sandbox build
Verified: `rw_steward_stock_set` and `rw_steward_stock_run` are NOT present in the sandbox tool table
(both raise `NameError: Unknown function`). The documented allow_saplings fix cannot be applied via tool.
Re-verified root cause this pass: forestry job still `allow_saplings: False` (read via rw_steward_stock_list),
so it only cuts growth>=1.0; poplars near home are 0.57-0.88 growth -> "no valid trees (count 12 / target 500)",
61 runs without targets. The 3 usable poplars (growth 0.69-0.88) refuse manual cut-designate too in this build
("not haulable"). Net: wood was stuck at 12 logs all day 7-8.
LESSON (all games): before applying any journal fix, probe whether its tool exists in the CURRENT sandbox build — call it and catch `NameError: Unknown function`. The RimBridge sandbox exposes a SUBSET of tools per build (this episode: rw_steward_stock_set / rw_steward_stock_run absent, so the allow_saplings=True fix is unapplyable; wood stalls at 12 logs). When a documented fix's tool is absent, fall back to the next control level (rw_ui_designate cut on growth>=0.6 trees if it exists) or plan around the resource. Never burn steps assuming the fix tool works.
