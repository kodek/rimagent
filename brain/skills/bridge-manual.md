---
name: bridge-manual
description: Operator's manual for the RimBridge tools, how to sense the map, which control altitude to use for each kind of action, the Steward (stock targets and work priorities as policy), the engine escape hatch, the think-step protocol, and the pitfalls that waste steps.
tags: [tools, bridge, protocol, manual, always]
always: true
---
# RimBridge operator's manual

Every bridge RPC `a.b` is a tool named `rw_a_b`; its documented params go at the top level of the call (e.g. `rw_ui_build(def="Wall", rect=[60,60,5,4])`). Results are JSON, truncated at ~8k chars, ask narrowly (filters, `limit`, small `w`/`h`) instead of dumping everything. Bridge errors come back as `{"error": ...}`; read them, they name the missing param or the reason a cell failed.

## 1. The three senses

**Structured reads (facts).** Start every step with `rw_state_summary` (date, colonists with id/name/pos/mood/job/top skills, wealth, food_days, threat_points, alerts, pending_letters, zones, blueprints, power, key_stocks). Then narrow down:
- `rw_state_alerts`, the alert bar with explanations; `rw_state_letters`, letters on screen with `id` and choices.
- `rw_state_pawns(filter=colonists|prisoners|animals|hostiles)`; `rw_state_pawn(pawn="Sparky")`, skills, traits, health, needs, mood thoughts, gear, work priorities.
- `rw_state_threats`, hostiles with weapons and distance to home, plus storyteller threat points.
- `rw_state_stocks(category=Foods)`, `rw_state_storage`, `rw_state_research`, `rw_state_rooms`, `rw_state_designations`, `rw_state_bills(thing=...)`, `rw_state_quests`.
- `rw_map_find(kind=item|tree|resource_rock|animal|corpse|chunk|building|blueprint, def=..., near=[x,z], radius=, forbidden=true, limit=)`, things sorted by distance from home. This is how you find loose wood, forbidden crash-pod steel, huntable deer, ore.
- `rw_map_cell(cell=[x,z])`, `rw_map_open_rects(w=8,h=6,near=,limit=)` (free buildable rectangles, returns min corners), `rw_map_terrain_stats`, `rw_map_path`, `rw_map_reachable`.
- `rw_defs_buildable(category=Structure|Production|Furniture|Power|Security|Misc|Floors)`, what you can build right now with costs; `rw_defs_get(def=...)` for any def's stats/recipes/research; `rw_defs_search(query=)`; `rw_defs_work_types`.

**`rw_map_view` (layout).** ASCII, one char per cell. Params `x, z` = **min corner** (or `center=true`), `w, h` up to 150, `layer=all|terrain|buildings|zones|pawns|items|roof|fog|home`. Default is centred on home, 60x40. Legend:
`? fog | @ colonist | ! hostile | a colony animal | w wild animal | n other pawn | # wall | + door | ^ rock | o ore | b bed | t work table | s stove/campfire | r research | g power | % turret | x other building | p blueprint/frame | S stockpile | G growing zone | ~ water | T tree | , plant/crop | i item | * fire | f fertile soil | : sand/gravel | - floor/road | . ground`.
The roof layer uses `R` thick rock (unminable-overhead, no drop pods), `r` thin natural, `c` constructed, `.` none. The home layer marks `H`.

**Coordinate convention.** x grows to the **right**, z grows **up** (the top printed row is max z). Every cell is a `[x, z]` array. Every rect is `[minX, minZ, w, h]`, so `[60,60,5,4]` covers x 60..64, z 60..63. Row labels on the left are z; the header digits mark every 10th x. Pawn `pos` and thing `pos` use the same `[x,z]`.

**`look` (a picture).** `look(x, z, w=60)` renders the real map as an image. Use it for a sanity check of a layout or to understand something the ASCII cannot show; use `rw_map_view` for exact coordinates. It does not move the human's camera; `rw_ui_select(thing=...)` does, for the human watching.

## 2. Control altitudes (pick the lowest that works)

0. **Policy: the Steward (`rw_steward_*`, section 2b).** Stock targets, work priorities and the standing orders (draft, rescue, unforbid, corpses, beds, policies, blueprints, fire) are kept by the mod every tick. Before you designate trees/ore/animals, type priorities, draft everyone or unforbid a pile, ask whether a target, a posture, a rally point or an order toggle says the same thing once.
1. **Right-click menu: `rw_ui_orders_at` / `rw_ui_order`.** Exactly what a player gets by right-clicking with a pawn selected: pick up, equip, eat, rescue, tend, prioritize hauling, prioritize construction, attack, capture. `rw_ui_orders_at(pawn="Manu", at="Steel2851")` lists `[{label, disabled, priority}]`; `rw_ui_order(pawn="Manu", at="Steel2851", label="haul")` runs one (label is a substring match; `i` picks by index). A `disabled` entry tells you why ("incapable of violence", "forbidden", "no path"). Works on cells (`at=[x,z]`) and thing ids.
2. **Buttons: `rw_ui_gizmos` / `rw_ui_press`.** The gizmo bar of a selected thing: Draft, Fire at will, Hold fire, Rest until healed, Copy/Paste bills, Toggle power, Rearm, Rename, Prioritise. `rw_ui_gizmos(thing="Human102")` then `rw_ui_press(thing="Human102", label="draft")`. Targeted gizmos (throw, cast, fire mortar) take `target`.
3. **Designators: `rw_ui_designate`.** `designator=mine|cut|harvest|harvestwood|hunt|haul|deconstruct|cancel|uninstall|tame|slaughter|strip|open|smooth|removefloor|claim|forbid|unforbid|plan|unplan` (or any `Designator_ClassName`), applied to `cells=[[x,z],...]`, `rect=[x,z,w,h]`, or `things=[ids]`. This is how you queue work for the whole colony rather than one pawn. Wood, berries, meat and steel are queued by the steward's stock jobs; designate them yourself only for a one-off (a tree blocking a blueprint, ore under a planned room, a specific animal). For a one-off tree use `cut`, not `harvestwood`: while forestry is below target it adopts every `harvestwood` designation on the map and releases them all when the target is met; `cut` (CutPlant) is never adopted. Ore and animals have no non-adopted designator: place the one-off when the matching job is at target, or `rw_steward_stock_set(kind=, suspended=true)` for the duration.
4. **Blueprints: `rw_ui_build`.** `def` (ThingDef or TerrainDef), then one of `at=[x,z]`, `line=[[x1,z1],[x2,z2]]`, `rect=[x,z,w,h]` (+`fill=true` for a filled area, default outline). `rot=N|E|S|W` for beds/tables/doors when orientation matters. `stuff` is chosen automatically (most plentiful allowed material) unless you pass e.g. `stuff="BlocksGranite"`. Pass `dry_run=true` first for big placements: it returns `placed`, `failed` (cell + reason), `cost_each` and `work`. Floors are TerrainDefs (e.g. `WoodPlankFloor`), placed the same way.
5. **Zones: `rw_ui_zone`.** `action=create_stockpile|create_growing|delete|add_cells|remove_cells|set_plant|rename|set_priority`, with `rect`/`cells`, `label`, `plant="Plant_Rice"`, `priority=Low|Normal|Preferred|Important|Critical`, `preset=DefaultStockpile|DumpingStockpile`. Storage filters: `rw_ui_storage(zone="main", allow=[...], disallow=[...], priority=...)`. Home area: `rw_ui_area(action=home_add, rect=...)`.
6. **Colony management.** `rw_ui_set_work(pawn, priorities={"Cooking":1,"Growing":2,"Hauling":3})` (1 = highest, 4 = lowest, 0 = off; switches on manual priorities **and takes the pawn out of steward management**: the result says `steward_managed: false`; `rw_steward_pawn(pawn, managed=true)` hands it back). `rw_ui_set_schedule(pawn, hours="SSSSSSWWWWWWWWWWWWJJJJSS")` (24 chars, hour 0 first, A/S/W/J/M). `rw_ui_set_policies(pawn, food=, apparel=, drug=, area=, medical=NoCare|NoMeds|HerbalOrWorse|NormalOrWorse|Best, hostility=Flee|Attack|Ignore, self_tend=)`. `rw_ui_set_research(def="Electricity")`. `rw_ui_add_bill(thing=<table id>, recipe="CookMealSimple", mode=TargetCount, count=10)` then `rw_ui_bill(thing, index, action=set|suspend|resume|delete|top, count=, radius=)`. `rw_ui_prisoner`, `rw_ui_animal`.
7. **Combat: `rw_ui_draft` / `rw_ui_goto` / `rw_ui_attack`.** `rw_ui_draft(pawn, drafted=true)`; `rw_ui_goto(pawn, cell=[x,z])` drafts automatically (pass `draft=false` for an undrafted walk); `rw_ui_attack(pawn, target=<hostile id>, melee=false)`. Drafted pawns do not eat, sleep or work: undraft when the fight ends. Each of these makes the `combat` order leave that pawn alone for ~2500 ticks, so it will not undraft a pawn you drafted. `rw_ui_cancel_job(pawn)` interrupts.
8. **Letters and quests: `rw_ui_letter`.** `rw_state_letters` gives `id` and `choices`; `rw_ui_letter(id, action=choose, choice="Accept")` or `action=dismiss`. Unanswered letters pile up and some expire.
9. **Direct jobs: `rw_ui_job` (last resort).** `rw_ui_job(pawn, job="Ingest", target="MealSimple1234")`, `job="Equip"`, `"Wear"`, `"Rescue"`, `"TendPatient"`, `"HaulToCell"` (`target` = thing, `target_b` = cell), `"Research"`. Use it only when no order/gizmo/designator does the thing; it bypasses the game's own checks and often fails silently if the pawn cannot reach or is incapable.

Game clock: `rw_game_speed(speed=0..3)` (0 pause, 1 normal, 2 fast, 3 superfast), `rw_game_pause(paused=)`, `rw_game_status`, `rw_game_save(name=)`. The runner slows the game to normal speed while you think and restores fast speed after `end_turn`; do not leave the game paused on purpose.

## 2b. The Steward: policy, not chores

Two engines inside RimBridge run every tick without you: the **scorer** (Free Will) sets each managed colonist's work priorities from skills, passions, colony needs and your posture; the **stock keeper** (Colony Manager Redux) designates cut/harvest/hunt/mine until counted stock meets a target. Both default on. The situation packet carries a "Steward" block (posture, one line per stock job `wood 420/500 ↑ forestry ok`, problems, unmanaged pawns) and `rw_state_summary.steward` a brief. Stock kinds: `forestry`, `foraging`, `hunting`, `mining`, `production`, `livestock`. Posture presets: `defend`, `build`, `harvest`, `recover`, `normal`; or custom deltas.

| Tool | Example | Returns |
|---|---|---|
| `rw_steward_status` | `rw_steward_status()` | `{enabled:{scorer,stock}, posture, pawns:[{id,name,managed,priorities,top:[{work,priority,why}]}], stock:[{id,kind,label,target,current,enabled,suspended,managed,last_run_hours_ago,designations,failures,summary,notes}], problems:[...]}` |
| `rw_steward_enable` | `rw_steward_enable(stock=false)` | `{scorer: true, stock: false}`; omit a key to leave it |
| `rw_steward_pawn` | `rw_steward_pawn(pawn="Sparky", managed=false)` | `{pawn, managed}`; unmanaged pawns keep whatever `rw_ui_set_work` gave them |
| `rw_steward_explain` | `rw_steward_explain(pawn="Jen", work="Cooking")` | `[{work, priority, score, reasons:[{label, delta}]}]`; omit `work` for every work type, sorted by priority |
| `rw_steward_posture` | `rw_steward_posture(label="build", hours=12)` or `rw_steward_posture(label="frost", hours=8, work={"PlantCutting":0.6,"Research":-0.5}, targets={"forestry":1.5})` | the posture `{label, expires_in_hours, work, weights, targets}`; `rw_steward_posture(clear=true)` -> `null` |
| `rw_steward_stock_list` | `rw_steward_stock_list()` | stock rows plus `allowed:[defName]` and per-kind settings |
| `rw_steward_stock_set` | `rw_steward_stock_set(kind="forestry", target=800)`; `rw_steward_stock_set(kind="hunting", suspended=true)`; `rw_steward_stock_set(kind="mining", allow=["ComponentIndustrial","Plasteel"], max_radius=90)` | the job row. `id` is the integer from the `stock` rows of `rw_steward_status`/`rw_steward_stock_list` (`id=4`, never `"mining1"`); `kind` works when there is exactly one job of that kind (several -> the error lists the ids). Mining `allow` names are *product* ThingDefs (what `stock_list` shows under `available`: Steel, ComponentIndustrial, Plasteel, Gold, Uranium; labels like "plasteel" also work), not rock defs like MineablePlasteel; the mining allow list doubles as the counted filter, so keep Steel in it (allow adds, disallow removes) unless the target is meant for the rare product alone |
| `rw_steward_stock_add` | `rw_steward_stock_add(kind="production", recipe="CookMealFine", target=10)` (optional `table=<stove thing id>`); `rw_steward_stock_add(kind="livestock", species="Chicken", max=6)` | the new job row. Production takes `recipe` (a RecipeDef, e.g. CookMealSimple, CookMealFine) and no `allow`/`disallow` (the recipe is fixed at add time); one job per recipe, and a `Production (simple meals)` job already exists once a stove/campfire does (adjust it with `stock_set`). Livestock takes `species` (PawnKindDef) plus `min`/`max` (`target` = max); on livestock jobs `allow`/`disallow`/`train` name trainables (Obedience, Release, Rescue, Haul), not species; a second job for the same species is refused |
| `rw_steward_stock_remove` | `rw_steward_stock_remove(kind="livestock")` or `rw_steward_stock_remove(id=5)` | `{removed: true}` |
| `rw_steward_stock_run` | `rw_steward_stock_run(kind="forestry")` or `rw_steward_stock_run(id=1)` | `{ran, summary}`; forces one pass now instead of waiting for the interval |
| `rw_steward_settings` | `rw_steward_settings()` to read; `rw_steward_settings(scorer={"ConsiderBestAtDoing":1.0, "globalWorkAdjustments":{"Research":0.3}}, stock={"MaxWorkRadius":90, "HuntPredators":false})` | `{scorer:{...all fields}, stock:{...}}`. Writes the RimBridge **mod settings file**: it survives new games, episodes and restarts (the notebook does not); prefer a posture for anything per-colony, and reset a work adjustment with `rw_steward_settings(scorer={"globalWorkAdjustments":{"Research":null}})` (scalar fields must be set back to their default value explicitly) |
| `rw_steward_research` | `rw_steward_research()` reads; `rw_steward_research(queue=["Electricity","Batteries"])` replaces the queue; `append=true` adds to the end; `clear=true` empties it | `{queue:[defName], queue_detail:[{def,label,available,progress}], current, current_progress, started?, skipped?}`. An ordered research queue the steward advances itself: when nothing is being researched the first startable queued project is set as current right away, otherwise it starts when the current project finishes (`clear` does not cancel the current project; `rw_ui_set_research(def=)` picks one project immediately and does not touch the queue). Caretaker stream only in parallel mode |

**Standing orders** (`rw_steward_orders`): eight reflexes in the mod, each toggleable and explainable, ids `combat`, `rescue`, `unforbid`, `corpses`, `beds`, `policies`, `blueprints`, `fire`. A manual action on a pawn or thing (draft/goto/attack, forbid/unforbid, set_policies, a press on a bed, a Rescue/TendPatient job) pauses the matching order for that target for ~2500 ticks (beds, food policy and heater targets: 2 days; medical care set by hand or changed outside the order: never touched again by the order, set it back yourself). The Steward block shows `orders: combat(rally set) rescue ...` with ✗ on disabled ones and a summary for any order that acted since the last step.

| Tool | Example | Returns |
|---|---|---|
| `rw_steward_orders` | `rw_steward_orders()` | `[{id, label, enabled, interval_ticks, last_run_hours_ago, summary, acting_on}]`, one row per order |
| `rw_steward_orders_set` | `rw_steward_orders_set(id="corpses", enabled=false)`; `rw_steward_orders_set(id="all", enabled=true)` | the row (`id="all"` -> every row) |
| `rw_steward_orders_rally` | `rw_steward_orders_rally(rect=[108,112,4,2])` sets; `rw_steward_orders_rally()` reads; `rw_steward_orders_rally(clear=true)` | `{rect}` or `null`; without a rect the combat order holds fighters at the base centre |
| `rw_steward_orders_explain` | `rw_steward_orders_explain(id="combat")` | `{id, doc, rules:[...], hands_off:[{thing/pawn, until_hours}]}`: what it does and which pawns/things it is currently leaving to you |
| `rw_steward_orders_run` | `rw_steward_orders_run(id="rescue")` | `{ran, summary}`; forces a pass now |

Rules: read `rw_steward_status` before touching work or stock; `rw_steward_explain` before any override; posture for the next 6-48 h, `rw_steward_settings` for the colony's standing shape, `rw_steward_pawn managed=false` for one pawn with one fixed role (hand back when done). Never set priorities on a managed pawn, the next pass overwrites them. Never designate what a stock job already covers. Nothing in `steward.*` marks the game assisted. Set the rally point on day 1-2 (defense-basics); toggle an order off only for a stated reason and turn it back on. Numbers and defaults: manager-patterns and work-priorities.

## 3. The escape hatch: engine access

`rw_engine_get(path)`, `rw_engine_set(path, value)`, `rw_engine_call(path, args=[...])`, `rw_engine_members(path|type)`, `rw_engine_types(query)`, `rw_engine_new(type, args|fields)` walk the live object graph by reflection. Path roots: `Find`, `Current`, `Map`, `World`, `Game`, `Player`, `Thing:<id>`, `Pawn:<name|id>`, `Def:<DefType>:<defName>`, `Type:<Full.Name>`, `Zone:<label>`, `Area:<label>`, `Faction:<name>`, `Room:<id>`. Segments: `.member`, `.method()` (parameterless only in paths; methods with args go through `rw_engine_call` with `args`), `[index|key|defName]`. Args are coerced: cells as `[x,z]`, things by id, defs by defName, enums by name.
Examples that work: `Pawn:Sparky.needs.food.CurLevel` -> `0.79`; `Find.CurrentMap.weatherManager.curWeather.defName`; `Def:ThingDef:Plant_Rice.plant.growDays` -> `3.0`; `Map.mapTemperature.OutdoorTemp` (a property, so no `()`); `Zone:rice1.cells`; `rw_engine_call(path="Map.listerThings.ThingsOfDef", args=["Steel"])`.
Before guessing, find the real name: `search_source("class Building_Turret")`, `find_source_files("StorytellerUtility")`, `read_source(path, start, end)` on the decompiled 1.6 source, or `rw_engine_members(path="Pawn:Sparky.needs")` to list fields/properties/methods. Reading is free; `engine.set`/`engine.call` can put the game in states the UI never would, prefer the UI tools, use the engine when they cannot express what you need (e.g. reading `Find.Storyteller.difficulty`, a hediff's severity, a plant's growth percent). Some namespaces (System.IO, Prefs, mod loading) are blocked.

## 4. The ledger, events and wake-ups

The mod keeps an append-only event ledger: `letter`, `message`, `incident`, `hostile_group`, `hostile_group_gone`, `colonist_downed`, `colonist_died`, `pawn_died`, `mental_break`, `research_finished`, `built`, `building_lost`, `quest`, `colonist_joined`, `colonist_left`, `day`, `game`. Each has `seq`, `kind`, `text`, `tick/day/hour`, optional `cell`, `thing`, `data`. The runner hands you the events since your last step at the start of each step, and watchers (`brain/watchers/*.py`) see them every ~0.5 s of real time without the LLM. Use `wake_on` in `end_turn` to be woken by a kind (default kinds: letter, incident, colonist_died, colonist_downed, mental_break, hostile_group, quest, building_lost).

## 5. Dev tools and the "assisted" flag

`rw_dev_spawn`, `rw_dev_spawn_pawn`, `rw_dev_incident(def="RaidEnemy", points=)`, `rw_dev_god_mode`, `rw_dev_heal`, `rw_dev_set_need`, `rw_dev_finish_research`, `rw_dev_weather`, `rw_dev_destroy`, `rw_dev_damage`, `rw_dev_kill_hostiles`, `rw_dev_reveal_map` exist for drills. **Any dev call permanently marks the current game `assisted: true`** (visible in `rw_game_status`, the ledger and the scorecard). Assisted games are recorded separately and never count as honest scores. Never use them to rescue a scored run.

## 6. The think-step protocol

A step is one LLM conversation with a tool budget (~30 calls). Every step **must end with `end_turn(notes, wake_in_hours, wake_on)`**, until you call it the game crawls at normal speed; pawns do execute your orders as soon as you give them. `wake_in_hours` is in-game hours (default 6; use 1-2 during a raid or a fire, 8-12 when things are calm), `wake_on` is a list of event kinds that should wake you early. `end_episode(reason)` declares the game lost or hopeless. Order of work inside a step: read (`rw_state_summary`, alerts, letters, new events) -> decide the single most urgent thing -> act -> a quick verification read (`rw_state_designations`, blueprint count, `rw_ui_orders_at` result) -> `notebook_append` if something notable happened -> `end_turn`.

## 7. Pitfalls

- **Crash-landed items start forbidden.** The `unforbid` order clears items in the home area or within 20 cells of the base centre and drop-pod contents within 40 (never colonist corpses, hostile-camp loot, trade goods, or a thing you forbade in the last hour). `rw_map_find(kind=item, forbidden=true)` lists what is left; `rw_ui_designate(designator=unforbid, things=[ids])` or a `rect` for loot that fell farther out. Nobody hauls forbidden things.
- **`rw_state_stocks` counts unforbidden things on the map, `key_stocks` in the summary only stored ones.** Loose logs in the forest are invisible to both until they lie in a stockpile; use `rw_map_find(def="WoodLog")`.
- **You need a stockpile before hauling works** (`rw_ui_zone(action=create_stockpile, rect=..., label="main")`). Put it under a roof; steel and food in the rain is fine, but corpses and rot are not.
- **Walls need a door** or the room is sealed and pawns path around; **roofs need walls** (a roof grows automatically over an enclosed room; unsupported roof further than 6 cells from a wall collapses). A room is only "indoors" (temperature, mood) when enclosed and roofed.
- **Work priorities belong to the steward.** 1 = highest, 4 = lowest, 0 = off. `rw_ui_set_work` unmanages the pawn (its result says `steward_managed: false`) and the scorer stops touching it until `rw_steward_pawn(managed=true)`. Setting priorities on a managed pawn is overwritten within a minute. A pawn "incapable" of a work type cannot be assigned it (the tool errors).
- **Speed.** The runner runs the game at normal speed while you think (a step costs 1-3 in-game hours) and at fast speed between steps. Do not call `rw_game_pause(paused=true)` yourself except mid-combat for a single precise order, and unpause before `end_turn`.
- **Truncation.** Results are cut at ~8k chars. Use `limit`, `category`, `filter`, small map windows, and `layer=` to keep results short; a truncated result is a wasted call.
- **Thing ids** look like `Steel2851`, `Human102`, `WoodLog2861`; pawns are accepted by name (`"Sparky"`) or id. Ids change between games, never hardcode them into skills.
- **Blueprints need materials on the map and a builder with Construction enabled.** `rw_state_summary.blueprints` staying constant across steps means nobody is building: check materials (`failed` reasons, stocks), priorities, forbids and reachability.
- **Growing zones only accept fertile terrain** (`f` in the view, fertility > 0); soil under trees must be cleared with `cut` first. `set_plant` requires the plant's research.
- **Drafted pawns freeze colony work.** The combat order undrafts what it drafted 600 ticks after the last hostile leaves; pawns you drafted by hand are yours to undraft. Check `drafted: true` in the summary at the start of each calm step.
- Bills need a work table id from `rw_map_find(kind=building, def="Campfire")` or `rw_state_summary`; `rw_defs_get(def="Campfire")` lists the recipe defNames.

## 8. Worked examples

**A. Day-1 stockpile (the loot unforbids itself)**
1. `rw_map_open_rects(w=8, h=6, near=[102,122], limit=3)` -> `[{at:[98,114]}...]`.
2. `rw_ui_zone(action="create_stockpile", rect=[98,114,8,6], label="main")`.
3. `rw_ui_storage(zone="main", priority="Important")`.
4. `rw_map_find(kind="item", forbidden=true, limit=40)` an hour later: the `unforbid` order has cleared the crash-pod loot near the base; `rw_ui_designate(designator="unforbid", things=[...])` only for pods that landed farther than 40 cells out.

**B. Rice field**
1. `rw_map_view(x=90, z=118, w=30, h=15, layer="terrain")` -> pick a block of `f` cells.
2. `rw_ui_zone(action="create_growing", rect=[101,123,6,6], plant="Plant_Rice", label="rice1")` -> `{cells: 36, failed: [...]}`.
3. Nothing else: the scorer gives Growing/PlantCutting to the best Plants pawn on its own (`rw_steward_explain(pawn="Jen", work="Growing")` to see it). If the harvest must happen before a frost: `rw_steward_posture(label="harvest", hours=12)`.

**C. A wooden room with a door, then beds**
1. `rw_ui_build(def="Wall", rect=[106,114,8,6], dry_run=true)` -> check `failed`.
2. `rw_ui_build(def="Wall", rect=[106,114,8,6])` (outline).
3. `rw_ui_build(def="Door", at=[110,114])`, the door replaces one wall blueprint on the south edge.
4. After `built` events / `blueprints: 0`: `rw_ui_build(def="Bed", at=[107,118], rot="S")` x3, then `rw_ui_build(def="Campfire", at=[112,111])` outside.

**D. Wood and steel (the steward's job)**
1. `rw_steward_status()` -> `stock: [{kind:"forestry", target:500, current:120, designations:24, ...}, {kind:"mining", target:300, current:60, ...}]`. It is already cutting and mining.
2. Need more for a stone base? `rw_steward_stock_set(kind="mining", target=600)`; in a hurry: `rw_steward_stock_run(id=<mining id>)`.
3. Only for a one-off (a tree on a blueprint cell, ore under a planned room): `rw_ui_designate(designator="cut", things=[...])` (cut, not harvestwood: while forestry is below target it adopts harvestwood designations and releases them when the target is met) / `rw_ui_designate(designator="mine", rect=[...])` (mining adopts these too; place it while the job is at target or suspend the job first).
4. Verify: `rw_state_designations` shows `HarvestPlant`/`Mine` counts; `problems` in the status names a stalled job.

**E. First raid**
0. Days earlier: `rw_steward_orders_rally(rect=[108,112,4,2])`, the cells inside the doorway behind the wall corners.
1. Woken by `hostile_group`. `rw_state_threats` -> ids, weapons, distance. `rw_steward_orders()` -> `combat` `acting_on: 2`, summary `drafted Manu, Jen to rally`; the pawn incapable of violence is restricted to Home.
2. `rw_steward_posture(label="defend", hours=6)`. Nothing else unless the raid is a breach or drop pods inside; then `rw_ui_goto`/`rw_ui_attack` the shooters you need (those pawns are hands-off to the order for an hour).
3. `rw_ui_attack(pawn="Manu", target="Human2331")` only for focus fire on the raider with a gun; `end_turn(notes="raid: combat order holding rally", wake_in_hours=1, wake_on=["colonist_downed","hostile_group_gone"])`.
4. On `hostile_group_gone`: the order undrafts and runs `rescue`; `rw_ui_draft(drafted=false)` only for the pawn you attacked with. `rw_steward_orders()` shows `rescue`/`corpses`/`unforbid` summaries; `rw_map_find(kind="corpse")` to decide what to smelt or gift.

**F. Cooking**
1. `rw_map_find(kind="building", def="Campfire")` -> `Campfire2977`.
2. Within ~1 h a `Production (simple meals)` job (CookMealSimple, target 10+4n, rescaled with colonist count) appears by itself and creates the do-until-X bill on the campfire (an `rw_ui_add_bill` of your own is harmless but redundant: the job adopts an existing CookMealSimple bill and deletes duplicates).
3. The scorer now raises Cooking for the best cook because a bill exists. Adjust with `rw_steward_stock_set(kind="production", target=30)` or `table="ElectricStove123"`; never add a second CookMealSimple job (two jobs share one bill and overwrite each other's count). A different recipe gets its own job: `rw_steward_stock_add(kind="production", recipe="CookMealFine", target=10)`; `allow` is not accepted for production. Check `rw_state_bills(thing="Campfire2977")` later.

**G. A letter with choices**
1. `rw_state_letters` -> `[{id: "Letter_1203", label: "Quest: ...", choices: ["Accept","Reject"]}]`.
2. `rw_ui_letter(id="Letter_1203", action="choose", choice="Reject")`.

**H. Engine read you cannot get elsewhere**
1. `rw_engine_members(path="Pawn:Sparky.health.hediffSet")` -> find `hediffs`.
2. `rw_engine_get(path="Pawn:Sparky.health.hediffSet.hediffs", depth=2)` -> each hediff with `def`, `Severity`, `Part`.
3. `rw_engine_get(path="Find.Storyteller.difficulty.threatScale")` -> `1.0` on Rough.

## The building camera: `rw_map_detail` (use it for every build)

`rw_map_detail(x=, z=, w=, h=)` or `rw_map_detail(around=<thingId|pawn>)` is a zoomed view (up to 60x60) where **every column is numbered** (read x down the three header rows: hundreds / tens / units; z is the row label), each building type gets its own letter (UPPER = built, lower = blueprint/frame, legend included), `*` marks interaction spots that must stay clear (benches, stoves, beds, tables), `+` doors, `_` stockpile, `,` growing zone, `i` items. It also returns `things` in view with id, rot, size and interaction_cell. Workflow for any construction:
1. `rw_map_detail` around the site → pick exact cells on the numbered grid.
2. `rw_ui_build(..., dry_run=true)` for anything with an interaction spot or footprint > 1x1; the failure reason tells you what blocks it; adjust `rot` (N/E/S/W moves the interaction spot) or the cell.
3. For a whole room or layout use one `rw_ui_build_many(ops=[...])`: e.g. `[{"def":"Wall","stuff":"WoodLog","rect":[130,120,9,7]}, {"def":"Door","stuff":"WoodLog","at":[134,120]}, {"def":"WoodPlankFloor","rect":[131,121,7,5],"fill":true}, {"def":"Bed","stuff":"WoodLog","at":[132,124],"rot":"N"}]`, walls as rect outline, floors as filled rects, then furniture. It returns one result per op; failed cells list the reason.
4. `rw_map_detail` again to verify (lowercase letters = your blueprints).
Rooms: leave at least one free cell around furniture, put the door on the side facing the base, keep 2-3 cells of walking space; a bedroom is at least 5x5 interior, a workshop 8x8. To enlarge an existing room, designate `deconstruct` on the wall segment, build the new outline, then a door.

## How you see the world (v2, read this order every step)

1. **Tracked values + "what changed"** open every step. They are computed by the harness from the engine; trust them and react to trends (food_days falling, a room gaining a PROBLEM, a colonist's mood dropping). Add your own with `watch_add(label, path)`; remove noise with `watch_remove`.
2. **The base as objects** (`rw_state_base`): rooms with `Room:<id>` refs, size, free floor, doors and where they lead, contents (with ids and interaction cells in verbose mode), problems (unroofed / no door / dark / cold / no free floor), structures outside rooms, anchors, TRAPPED colonists. Reason about rooms and objects, not cells.
3. **Locations are names, not numbers.** Everywhere a cell or rect is accepted you can write: `Campfire39256` (a thing), `@Gamble` (a pawn), `bedroom2` (an anchor you named), `bedroom2:NW` / `:N` / `:C` (corners/edges/centre), `bedroom2:inset:1` (interior), `bedroom2:extend:E:4` (the 4-wide strip beyond its east wall, how you extend a room), `Room:12`, `home`, and offsets `Campfire39256 +E2 +N1`. Name every room and site the moment you create it: `rw_anchor_set(name="bedroom2", rect=[139,127,6,5])` or `rw_anchor_set(name="kitchen", rect="Room:14")`. Then build with `rw_ui_build(def="Bed", at="bedroom2:NW +E1 +S1", rot="N")` and never do coordinate arithmetic in your head.
4. **The Steward block**: posture, one line per stock job (`wood 420/500 ↑ forestry ok`), problems and unmanaged pawns. A stalled job or an empty problems list is your cue; the numbers themselves are the steward's business.
5. **The building camera** (`rw_map_detail`) for exact placement, with anchors drawn in its legend; failed builds now return a mini camera with the failed cells marked `X` and the reason, read it before retrying.
6. **`look`** shows the real picture with a labelled 5-cell grid, anchor boxes, and numbered marks on every building/blueprint (red = planned, blue = built) plus a table number → id/def/cell, so what you see is addressable.
7. **`run_python` is a persistent REPL**: `beds = find(def="Bed")["things"]` stays available next step; `base()`, `summary()`, `detail(...)`, `build(...)`, `rpc(method, **params)` are pre-bound. Compute, don't guess.
8. Raw reads (`rw_map_find`, `rw_map_cell`, `rw_engine_get`) when you need a specific fact.
