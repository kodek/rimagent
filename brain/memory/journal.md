# Journal, lessons that survive between games


## 2026-09-16 18:51 (episode 1): ui.build needs explicit stuff
RimBridge build calls: ui.build and ui.build_many require an explicit `stuff` for any stuff-made def (Wall, Door, Bed, table, stool). Omitting it does NOT auto-pick a material — it returns the list of legal stuffs and places nothing, a silent no-op that looks like a failed build. Always pass stuff="WoodLog"/"BlocksGranite". Batch whole layouts (wall rect outline + door cell + furniture) into one ui.build_many call; the door op replaces the wall cell inside the same batch. Pending-blueprint counts grouped by def are the fastest way to see a stuck build.

## 2026-09-16 18:51 (episode 1): Steward buries everything under Hauling 1
Steward-managed colony artifact: when loose items lie around (e.g. right after landing), the steward scorer puts Hauling 1 on every pawn and Cooking/Construction/Research starve. Symptom: 0 meals while raw food sits in the stockpile, or a blueprint count frozen for a day. Diagnose in this order: (1) does the stove/campfire actually have a CookMealSimple bill, (2) is any pawn's Cooking > 0, (3) then bias away the Hauling with steward.posture(work={"Hauling":-0.5,"Cooking":0.5}) rather than hand-editing priorities (hand-editing ejects the pawn from steward management).
