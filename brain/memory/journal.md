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
