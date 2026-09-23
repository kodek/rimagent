
# Game: day 0 (new)
## Roster
- Robbins (Human165): Intel 8, Shooting 5, Construction 3 -> researcher + rifle (equipped Gun_BoltActionRifle)
- Jones (Human168): Crafting 6, Social 6, Intel 6 -> builder/crafter + revolver (equipped)
- Pumpkin (Human171): Plants 11, Animals 10, Mining 9, NONVIOLENT (cannot equip weapons) -> grower
## Base (built day 0, blueprints pending at 08h)
- Room 11x9 outline x113-123 z99-107, wood; door [118,99] (south)
- Beds (wood) [114,101]/[114,103]/[114,105] rot E; Campfire [120,104]; SimpleResearchBench [117,105] (footprint x116-118 z105-106)
- Stockpile "main": x125-132 z101-106
- Rice field "rice1": x126-135 z93-97, 39 cells, Plant_Rice (ripe ~day 3)
- Rally rect set: [114,100,9,7]
## State notes
- 41 blueprints pending (35 walls, door, 3 beds, campfire, bench). WoodLog on map ~483 vs need ~425 -> tight; DO NOT place more wood stuff until walls are built
- Table+stools cancelled (saved wood); re-add Table1x2c+2 Stool after walls built (food/mood)
- NO bullets anywhere on map: guns useless until bows (RecurveBow) or bullets (Machining). RecurveBow = research #1
- Research queue: RecurveBow (current) -> Smithing -> Batteries -> SolarPanels -> Pemmican -> Machining -> Gunsmithing
- Posture "buildout" 16h: Construction +0.5, Hauling -0.5
- Stock jobs: hunting target 120 (was 525); forestry 500; mining 300 (met); foraging 225
- Food: 19 survival meal packs (~10.9d) + rice coming; cooking bill NOT needed yet (meals already packaged)
- Wealth 17.3k: Steel 1170, Silver 800, stone chunks (slate/marble/sandstone) scattered NE of home; Stonecutting researched -> stonecutter table later
## Next step checklist
1. Verify enclosure: room_digest shows Barracks/Bedroom indoor, blueprints/frames -> 0 (door frame!); if stuck, keep Construction posture
2. Check work_matrix for zeroed rows (steward bug) -> fix with explicit rw_ui_set_work matrix
3. Add crafting bench (TableBench, wood) near stockpile for bow+arrow making; add bills when built
4. Add table+stools in room; consider torch/roof check; consider stone walls upgrade once blocks flow



## Day 4 15h — wood stall
- Wood: 19 stored (Jones hauled it in). No cut-designated trees. Forestry job stalled (80+ runs without targets).
- Nearby poplars (4, at 14-22 cells) REFUSE the cut designator: "no designation needed" / "not haulable". Cause unknown — possibly small-tree quirk or zone issue.
- Jones was repairing a wooden wall (97%) before sleeping. Robbins researching (RecurveBow 36%->~40%).
- Both moods recovering: Robbins 51-61, Jones 44-47.
- 19 wood is too low for any wood build. No blueprints pending.
- If forestry doesn't pick up trees by next check, try: (a) check if trees need a "harvest" designation not "cut", (b) check growing zone / home area coverage, (c) use engine to force-designate.

- Wood down to 5 (table/stool/pin blueprints CANCELLED to save builder time; re-add when wood flows). 3 trees cut-designated, Jones cutting poplar now. Forestry job still stalled (no valid trees in its search radius).
- CraftingSpot built at [124,101] (no wood cost) — for bows/arrows after RecurveBow research completes.
- Thilia visitors (5) still wandering south of base [109-121, 110-121]. Uninteractable (no trade dialog). Will leave on their own.
- Robbins mood 20 (improving from 13, now relaxing socially). Jones mood 53 (cutting trees).
- Research: RecurveBow 32%.
- Alerts: Major break risk (Robbins, improving), Need defenses, Colonist left unburied, Need recreation variety (3 types needed, have 2).

- FRACTION: named (dialog answered: Hinbonhadinor / Ithtoville). 2 colonists now (Pumpkin DIED day ~3, blood loss — cause never pinned down; letter said "Blood loss").
- Pumpkin's corpse: at [114,101] IN the barracks (Room:67), unburied (alert: "Colonist left unburied"). Grave not yet placed (0 graves on map). "open" designator refused her ("no designation needed"). Mourning-of-Humanity ritual letter active until day ~14: needs a GRAVE containing her corpse. BUTCHER SPOT exists (outside rooms, near stockpile) + standing ButcherCorpseFlesh bill — watch: she may get butchered instead of buried (mood loss for the funeral). If butchered before burial, funeral is impossible.
- Mood: Robbins 13 (CRITICAL, below break threshold 35) — sleeping now (safe while asleep). Thoughts: Recreation-deprived -10, Awful barracks -7, friend died -5.6, Slept in heat -4, Ate without table -3. Jones 54 (ok).
- Work matrices set manually (steward zeroed artifact): Robbins Research 1 / Construction 2 / PlantCutting 2 / Hauling 3; Jones Doctor 1 / Crafting 2 / Construction 2. Both now UNMANAGED -> combat order will NOT auto-draft them (episode-2 lesson). On hostile_group: draft armed pawns myself.
- Posture "recovery" 36h set (Construction +0.5, Research +0.5, PlantCutting +0.4, Hauling -0.5, Growing +0.2, Hunting -0.5).
- Rally rect SET: [114,100,9,7] (50 cells, the barracks).
- Room:67 Barracks 9x7 BUILT (3 beds, campfire, research bench, animal sleeping spot). Door [118,99]. No roof. 30C outside, 29C in room -> "Slept in heat".
- Research: RecurveBow 32% (queue: RecurveBow -> Smithing -> Batteries -> SolarPanels -> Pemmican -> Machining -> Gunsmithing). No bullets on map; arrows are the only real weapon once TableBench built.
- Wood: 24 logs only (room build consumed the stock). 3 trees cut-designated (forestry stalled: no valid trees left near home within its radius; most nearby trees are stumps). Wood is the bottleneck for all further builds.
- Stockpile "main" x125-132 z101-106: 11 free cells. 2 forbidden stacks (BlocksMarble 5 loose).
- Visitors: 5 Thilia pawns (Antonina, Wise, Lamp, Squirt, Greene — Greene is Jones' GRANDMOTHER!) wandering at [111-122, 112-118], just SE of the room (room ends z99; they're at z112-118, ~15 cells south). They have trade items. Letters 2 & 6 (visitor) dismissed. Watch them; they may open a trade window or leave.
- Monolith (VoidMonolith38026) at [80,63] — 56 cells NW. Positive event; investigate later (free research/loot). Not urgent.
- Prairie dog MANHUNTER: dead (killed day ~0, Meat_PrairieDog 8 stored). Danger None.
- Kenya (Yorkshire terrier) at [122,102] — inside/near barracks. Pets order wants a "PetSafe" area (not yet created).
- Food: 43 meals stored (38 survival packs + 5 simple + 8 meat). Rice field ripe ~day 3-4. Foraging 5. food_days ~13.8. OK.
- Alerts: Major break risk (Robbins), Need defenses (raids starting soon — no sandbags/traps), Colonist left unburied, Need recreation variety (2 types, need 3: add HorseshoesPin or ChessTable).
- DEFENSE STATE: 2 pawns, both armed (rifle/revolver, NO AMMO). Rally rect set. No walls beyond the barracks, no traps. First raid likely day 5-10.
