---
name: manager-patterns
description: How to run the steward's stock targets (forestry, foraging, hunting, mining, production, livestock) and the work-priority scorer as policy instead of chores. Defaults, when to raise or lower targets (winter, big colony), when to suspend (raid, toxic fallout), the production job for meals, livestock opt-in, and how to read the problems list. Pull in when the Steward block shows a stalled job, a target you disagree with, or when you catch yourself hand-designating trees, ore or animals.
tags: [automation, steward, stock, work-priorities, colony-manager, free-will, posture]
always: false
---
# The steward does the chores

Two engines run in C# every tick, no LLM: the **stock keeper** (Colony Manager Redux, rewritten synchronous) keeps counted stock at targets by designating cut/harvest/hunt/mine; the **scorer** (Free Will) sets work priorities. You set targets, postures and exceptions; you do not designate trees or type priorities. If you find yourself doing either, fix the target instead.

# Pattern 1: stock targets

`rw_steward_stock_list` -> one row per job: `{id, kind, label, target, current, enabled, suspended, managed, last_run_hours_ago, designations, failures, summary, notes, allowed}`. `current` counts stored + loose unforbidden things on the map, so a pile of logs in the forest counts once it is unforbidden.

## Defaults (created on the first tick of a new colony, scaled by colonist count n)
| kind | counts | target | interval | notes |
|---|---|---|---|---|
| forestry | WoodLog | 500 + 100 x max(0, n-3) | ~1 h (2500 ticks) | no saplings, home radius 70 |
| foraging | berries and other wild edibles | 150 + 25 n | ~1 h | harvest designations on wild plants |
| hunting (meat) | raw meat, any kind | 300 + 75 n | ~2 h (5000 ticks) | `hunt_predators=false`; 0% revenge species first |
| hunting (leather) | leather | 100 | ~2 h | |
| mining | Steel | 300 + 50 x max(0, n-3) | ~1 h | hauls chunks, checks roof support and room division |
| production | products of one RecipeDef | CookMealSimple: 10 + 4n, added by itself once a stove/campfire exists; other recipes: you set it | ~1 h | one job per recipe; binds one do-until-X bill and removes duplicate bills of that recipe |
| livestock | one species (opt-in) | you set `max` (`target` = max) | | tame wild ones, slaughter above max, keep breeding pairs |
Auto-scaled targets are rescaled when colonists join or die (`ScaleTargetsWithColonists`); a target you set by hand is no longer rescaled (`auto_scaled: false` in `rw_steward_stock_list`; `rw_steward_status.stock` rows do not show it). `managed=false` is something else: the steward stops running that job entirely and drops it from `problems` (you designate by hand); use `suspended=true` to pause a job and keep it visible. Each run designates at most 40 things (`MaxDesignationsPerJob`) within `MaxWorkRadius` 70 of home and never within `DangerAvoidRadius` 30 of hostiles, hives or insects.

## When to change targets
- **Day 1**: leave the defaults. 500 wood is right for a wooden shelter plus campfire fuel; check `rw_steward_status.stock` once at the end of the day to see `current` moving.
- **Winter coming** (within ~15 days, temperature-and-seasons): `rw_steward_stock_set(kind="forestry", target=900)` (campfire burns ~10 wood/day; 3 colonists x 60 days of cold = 600+ fuel), `rw_steward_stock_set(kind="hunting", target=450)`, `rw_steward_stock_set(kind="foraging", suspended=true)` once nothing grows; mining unchanged. Hand-set targets stay put (no rescaling) until you change them, which is what a season needs. `rw_steward_posture(label="harvest", hours=48)` is for the last harvest push, not winter stocking: it raises Growing/Cooking/PlantCutting, multiplies foraging x1.5 and hunting x1.25 for 48 h, does not touch forestry, and expires. For a temporary blend use a custom posture, explicit targets override the preset: `rw_steward_posture(label="winter prep", hours=48, targets={"forestry":1.5,"hunting":1.5,"foraging":0}, work={"PlantCutting":0.3,"Hunting":0.2})`.
- **Stone or steel base going up**: mining 600; `rw_steward_stock_set(kind="mining", allow=["ComponentIndustrial","Plasteel"])` once you have Mining 8+. Mining allow names are the *product* ThingDefs (`rw_steward_stock_list` lists them under `available`: Steel, ComponentIndustrial, Plasteel, Gold, Uranium; labels like "plasteel" work too), not the rock defs (MineablePlasteel etc.). The allow list is also what `current` counts: allow adds, disallow removes, so keep Steel in it unless the target is meant for the rare product alone.
- **6+ colonists**: hunting meat 700+, forestry 900, and a second growing zone; meat rots in 2 days without a freezer, so do not raise meat above ~2 days of cooking (a pawn eats 1.6 nutrition/day; 1 meat = 0.05 nutrition, so 3 colonists eat ~100 meat/day).
- **Wealth discipline**: stock counts as wealth. Do not hold 2000 steel "just in case"; raise a target when a build plan needs it, then lower it.
- **Meat -15 mood** (killed innocent animal) hits the hunter: a lower meat target (150) and a rice field beats aggressive hunting in a 3-pawn colony with a fragile mood.

## When to suspend
- **Raid on the map** (`hostile_group` event, `rw_state_threats` non-empty): `rw_steward_stock_set(kind="hunting", suspended=true)` and forestry too if trees are outside the walls. Better: `rw_steward_posture(preset="defend", hours=6)` zeros both hunting targets (meat and leather) but only halves forestry/foraging/mining (x0.5, they keep designating toward half the target) and pulls Hunting -0.6 / Mining -0.4 / PlantCutting -0.4 for everyone; it expires by itself. If trees or ore are outside the walls, pass `targets={"forestry":0,"mining":0,"foraging":0}` on the same call (explicit targets override the preset) or `rw_steward_stock_set(kind="forestry", suspended=true)`. Resume with `suspended=false` or `rw_steward_posture(clear=true)` on `hostile_group_gone`.
- **Toxic fallout / volcanic winter**: suspend forestry, foraging and hunting (pawns outdoors take toxic buildup; animals are toxic to eat); mining is fine if the ore is under roof. Resume when the condition ends (ledger `message`).
- **Manhunter pack or a predator near home**: suspend hunting; `hunt_predators` stays false.
- **Cold snap / heat wave**: forestry and mining keep running; check no pawn is stuck outside without warm clothes.
- A suspended job keeps its target and resumes exactly where it was; a removed job (`rw_steward_stock_remove`) is gone until you `rw_steward_stock_add` it again.

## Production job for meals
The cook bill is the thing the scorer keys on: no bill, no Cooking priority for anyone. A `Production (simple meals)` job (CookMealSimple, target 10+4n, rescaled with colonist count) appears by itself within ~1 h of the first campfire/stove; it creates the bill, keeps it do-until-X at the target, unsuspended, and deletes duplicate CookMealSimple bills (operator tip: the campfire collects dupes). Do not add another CookMealSimple job: a second job for the same recipe shares the one bill and the two overwrite each other's count every run, so the rule is one production job per recipe. Adjust with `rw_steward_stock_set(kind="production", target=30)` (fixes the target, no more rescaling) or `table="ElectricStove123"`; 10 meals per colonist is a 2-day buffer, a fueled stove cooks 2x a campfire. Add a production job only for a different recipe: `rw_steward_stock_add(kind="production", recipe="CookMealFine", target=10, table=<stove id, optional>)`. Production jobs take no `allow`/`disallow` (the recipe is fixed at add time). Check `rw_state_bills(thing=<stove>)` once.

## Livestock (opt-in)
Only after you tame something: `rw_steward_stock_add(kind="livestock", species="Chicken", max=6)` keeps the herd at `max` by designating slaughter on the surplus (oldest and males first) and leaves breeding pairs (`tame` and `slaughter` default true, `min` 0). On livestock jobs `allow`/`disallow` (and `train`) name TrainableDefs (Obedience, Release, Rescue, Haul), not species: `species` picks the animal, `rw_steward_stock_set(id=<int>, max=N)` changes the cap later, and a second job for the same species is refused (use `stock_set`). Chickens double every ~5.7 days; without a cap they eat the crops. Do not add livestock for pack animals you want to keep (muffalo, alpaca) unless you want wool herds trimmed.

## Reading problems
`rw_steward_status.problems` and the ledger `steward` events tell you what the steward could not do; each is a decision for you, not a chore:
- `stock_stalled` (3 failed runs in a row or no targets for a day): forestry -> no trees within radius 70 (raise `max_radius`, or plant trees, or accept), hunting -> no safe animals (`hunt_predators=true` only with 2 shooters and a rifle, else lower the target), mining -> no exposed ore (mine into the mountain: `rw_ui_designate mine` on the rock over an ore vein once, the job continues from there), foraging -> season over (suspend).
- `stock_reached`: informational; if it keeps flipping, the target is at the noise floor (raise it 20%).
- "unmanaged pawn with everything disabled": `rw_steward_pawn(managed=true)` or set their priorities yourself.
- "no hunter with a ranged weapon": equip one (`rw_ui_order label="equip"`) or lower the meat target and grow more.
- `designations: 0, failures: 0, last_run_hours_ago > 3` with `current < target`: the job is suspended or stock is disabled (`rw_steward_enable(stock=true)`); check `enabled` in `rw_steward_status`.
- `current` far above target with designations still queued: the steward stops designating; already-designated things are still cut. Cancel with `rw_ui_designate(designator="cancel", rect=...)` only if the pawns are needed elsewhere.

# Pattern 2: the scorer and postures

Priorities 1..4 (1 first, 0 off) come from the scorer (see work-priorities for the numbers). Your policy levers:
- **Posture presets** (`rw_steward_posture(preset=, hours=12)`; `label=` naming a preset also works), exact tables from StewardTuning.Presets: `defend` (Doctor +0.3, Construction/Smithing/Firefighter +0.2, Hauling +0.1, Hunting -0.6, Art -0.5, Mining/PlantCutting -0.4, Research -0.3, Growing -0.2; ConsiderWeaponRange x1.5; hunting targets x0, forestry/foraging/mining x0.5), `build` (Construction +0.4, Hauling/Mining/PlantCutting +0.2, Smithing +0.1, Art -0.3, Research -0.2, Hunting -0.1; forestry and mining targets x1.5), `harvest` (Growing +0.4, PlantCutting/Hauling/Cooking +0.2, Hunting +0.1, Construction/Mining -0.2, Research/Art -0.3; ConsiderLowFood x1.5; foraging x1.5, hunting x1.25, forestry untouched), `recover` (Doctor +0.4, Cooking/Cleaning +0.2, Hauling +0.1, Construction/Research/PlantCutting -0.2, Mining/Hunting -0.3; ConsiderLowFood x1.25, ConsiderFoodPoisoning x1.5; all stock targets x0.75), `normal` = clear. `rw_steward_status.posture` shows the tables in force. Custom: `work={"Research":0.4,"Art":-0.8}` deltas -1..1 per WorkTypeDef, `weights={"ConsiderPassions":0.5}`, `targets={"forestry":1.5}`. One posture at a time; a new call replaces the old one; expiry raises `posture_expired`.
- **Global adjustments** (`rw_steward_settings(scorer={"globalWorkAdjustments":{...}})`) are permanent versions of posture work deltas, and "permanent" means the RimBridge mod settings file: they survive new games, episodes and restarts, unlike the notebook (reset per episode). Use them only for a standing shape you want in every colony; a posture is the per-colony lever. Reset a key with `rw_steward_settings(scorer={"globalWorkAdjustments":{"Research":null}})`; scalar fields (weights, MaxWorkRadius) must be set back to their defaults explicitly.
- **Weights** (`rw_steward_settings(scorer={"ConsiderBestAtDoing":1.0})`): 0 by default, which spreads work; 1.0 makes the best pawn at each skill own it (good from 5 colonists up). `ConsiderLowFood` 1.0, `ConsiderFoodPoisoning` 1.0, `ConsiderPassions` 1.0, `ConsiderBeauty` 1.0, `ConsiderOwnRoom` 1.0, `ConsiderMovementSpeed` 1.0, `ConsiderWeaponRange` 1.0, `ConsiderPlantsBlighted` 1.0, `TicksBetweenActions` 1 (raise to 5 if the game stutters).
- **Manual pawns** (`rw_steward_pawn managed=false` + `rw_ui_set_work`) are the exception for one pawn with one fixed role; hand them back when the reason is gone.

# What a watcher is still for
Reflexes the steward does not own: resume suspended jobs on `hostile_group_gone`, call `rw_steward_posture(label="defend")` the moment a raid lands, wake the planner on a letter you care about. Drafting, rescue, unforbidding, corpses, beds, food policy and fire belong to the standing orders (`rw_steward_orders`), stock and priorities to the scorer and stock keeper. A watcher that repeats any of those duplicates the steward and fights it (its manual touches even pause the order for the pawns it moves); delete it.
