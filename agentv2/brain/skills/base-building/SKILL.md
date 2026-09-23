---
name: base-building
description: Pull in when planning or placing walls, doors, roofs, floors, bedrooms/barracks, the home area, or choosing wood vs stone; also when a roof collapse, fire or "sleeping outside" mood problem shows up.
---
# Base building

## Structures: costs and numbers
| Def | Cost | Work | Base HP | Notes |
|---|---|---|---|---|
| Wall | 5 stuff | 135 x material factor | 300 x material | Supports roof up to 6 tiles away; 75% cover; blocks sight/fire lines. |
| Door | 25 stuff | 850 | 160 x material | Counts as wall for rooms/roof. Enemies treat closed doors like walls unless sapper/breacher. |

Materials: **Wood** 0.65x HP (195 HP wall), **100% flammable**, 0.7x work; **Steel** 300 HP, 40% flammable; **Sandstone** 420 HP, 0%, 5x work +140; **Granite** 510 HP, 0%, 6x work +140. Stone doors open at 0.45x speed (wood 1.2x). Blocks come 20 per chunk from a stonecutter's table (Stonecutting research). Only marble walls add beauty; granite is toughest.

**Rule:** first shelter in wood (fast, cheap); replace **walls** with stone as soon as blocks flow; keep **doors and furniture** wooden (fastest to open, safe inside non-flammable walls). Do not keep wood walls once electricity exists: a short circuit or dry thunderstorm burns the base. Stone wall sections act as fire breaks; fire crosses diagonal gaps, pawns cannot.

## "Placed" is not "built" and not "enclosed" (cost me 2 steps, ep.1)
- `ui.build` / `room()` / `ui.build_many` returning `placed` with **no `failed`** only means the **blueprints** went down. It says nothing about whether the walls got built or the room closed.
- A single **Door left as a frame** (blueprint, not built) keeps the room **"outdoors"**: beds/campfire count as outside and you get `slept outside` + `slept on the ground` + `slept in the cold` on every pawn (~-12 mood, mood 45 with food fine). The pawns will still build it eventually, but do not assume the room works until it is.
- **Verify enclosure with state, not with the build result:** `state.summary.room_digest` (or `state.rooms`) must show a `Barracks`/`Bedroom` row with a sane `cells` count and an indoor `temp`; `state.summary.blueprints` and `.frames` must both be **0**. Use my `step_brief` tool for that in one call.
- Build the door op **inside** the same `ui.build_many` batch as the wall rect (the door replaces that wall cell) — but then WAIT for it: keep a Construction posture until `frames==0`.

## Crashlanded day-0 shelter that worked (ep.1, temperate forest)
Wood walls `rect [119,97,11,9]` (11x9 outline), a wood **Door** in the south wall at the midpoint `[124,97]`, 3 **wood Beds** rot E at `[120,98]/[120,100]/[120,102]`, campfire `[128,103]` — **interior ~9x7 (63 cells)** roofs fully (roof reaches 6 tiles from any wall, so interiors up to 12 wide are fine). Warm-up needed only one Construction posture (+0.6) for ~16h to finish door frames. Result: `room_digest` -> `Barracks, 63 cells, temp 28C`.

## Bridge build pitfalls (cost me steps)
- **`ui.build` / `ui.build_many` require an explicit `stuff`** for anything stuff-made (Wall, Door, Bed, table, stool, torch...). Pass `stuff="WoodLog"` (or `"BlocksGranite"`). Omit it once ONLY to read back the list of legal stuffs with on-map quantities — omitting it is NOT an auto-pick: you get the options and no blueprint, a silent no-op.
- `ui.build_many(ops=[...])` places a whole layout in one call: `{"def":"Wall","rect":[x,z,w,h],"stuff":...}` (outline), then `{"def":"Door","at":[x,z],"stuff":...}` (the door op replaces that wall cell inside the same batch), then furniture cells. Far fewer calls than one build per piece.
- My tool `room(x,z,w,h,door="S",stuff="WoodLog",beds=0,dry_run=True)` does walls+door+beds with a per-op dry run; and `build_report()` lists pending blueprints grouped by def so a stuck build is obvious.
- A blueprint count that does not change for a day = no reachable material or no builder: check `stuff` availability, `state.designations` (forbids), and whether the steward buried Construction under Hauling (see work-priorities).

## Rooms and roofs
- A room = area fully enclosed by walls/doors/coolers/rock; corners are optional (but leak more heat). Use `rw_ui_build` with `rect` for walls and `at` for a Door on the traffic side.
- Roofs extend **6 tiles** from any wall/column, so interiors up to **12 wide** roof fully; wider needs interior columns/walls. Temperature control needs **>= 75% roofed**; under that the room snaps to outdoor temperature. 300+ unroofed tiles = "outdoors" (Slept outside, no room mood).
- Roofs are free and auto-designated over new rooms. Removing the last support within 6 tiles collapses the roof: thin/constructed roof deals **15-30 crush damage to head/neck** (roughly 1 in 3 kills an unhelmeted pawn); **overhead mountain** collapse destroys everything beneath. Lay a Remove-roof area before mining or deconstructing support walls. Trees cannot grow under roofs.
- Indoor items never deteriorate. Dark rooms give 80% work/move speed; a torch lamp is 10 wood for 10 days.

## Bedroom vs barracks
- Bedroom = only the owner's bed(s) (a lover pair is fine), no medical/prisoner bed; more than one unassigned bed makes a barracks. A barracks costs about **-5 mood vs an equivalent private bedroom** (-4 at higher quality). One barracks is fine on day 1; split into bedrooms within the first season.
- Impressiveness (bedroom/dining/rec mood): <20 awful, 20-30 dull, 30-40 mediocre, 40-50 decent, 50-65 slightly impressive, 65-85 impressive, 85-120 very impressive. It is weighted to the weakest of wealth/beauty/space/cleanliness, so a dirty floor drops a level. "Very impressive" needs a **5x5 or 4x6 interior**; 4x4 struggles. Returns diminish sharply.
- Space need (radius 7 walkable tiles): 1-3 = Confined -10, 4-10 = Cramped -5, 41+ = Spacious +5. Avoid 1-wide corridors and closet workstations.

## Floors
Floors stop wild plant growth, speed movement and remove the terrain cleanliness penalty (kitchen food poisoning, hospital, research). A 2-wide non-flammable strip is a fire break. Pawns pick up filth on soil (10%/step) and drop it on floors (5%/step), so floor the paths into the kitchen.

## Layout checklist (first days)
1. `rw_ui_zone` stockpile where the base will be and build around it (outdoor items take months to deteriorate).
2. Priority 1: walls + door for one ~7x7 room, beds (a normal bed saves ~1 hour sleep/day, avoids Slept on the ground), a 1x2 table + stools (avoids Ate without table).
3. Kitchen: raw-food shelf/stockpile **adjacent** to the stove (otherwise the cook hauls one meal's ingredients per trip); meal stockpile next door, later a freezer (coolers blue side in, fully enclosed and roofed, usually 2+). Keep fields, kitchen and freezer within a short walk.
4. Priority 2: wood-fired generator, conduits (buildings connect within 6 tiles), lamps, end table + dresser.

## Home area
Colonists **repair, clean and extinguish fires only inside the home area** (`rw_ui_area(action=home_add, rect=...)` / `home_remove`). Keep it tight around buildings and fields, add a 1-wide strip along critical conduits so short-circuit breaks self-repair, and widen it temporarily when a wildfire approaches.

Sources: Wall; Door; Roof; Rooms; Space; Thoughts; Wood; Stone blocks; Granite blocks; Sandstone blocks; Steel; Flammability; Floors; Home area; Basics
