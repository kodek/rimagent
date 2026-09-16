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
| production | meals (opt-in, see below) | you set it | | keeps a bill's count at the target |
| livestock | a tamed species (opt-in) | you set it | | slaughter above the count |
Auto-scaled targets are rescaled when colonists join or die (`ScaleTargetsWithColonists`); a target you set by hand stays fixed (`managed=false` on the row). Each run designates at most 40 things (`MaxDesignationsPerJob`) within `MaxWorkRadius` 70 of home and never within `DangerAvoidRadius` 30 of hostiles, hives or insects.

## When to change targets
- **Day 1**: leave the defaults. 500 wood is right for a wooden shelter plus campfire fuel; check `rw_steward_status.stock` once at the end of the day to see `current` moving.
- **Winter coming** (within ~15 days, temperature-and-seasons): forestry x1.5 (campfire burns 10 wood/day; 3 colonists x 60 days of cold = 600+ fuel), hunting meat x1.5, foraging to 0 or suspended (nothing grows), mining unchanged. Easiest: `rw_steward_posture(label="harvest", hours=48)` does the multipliers for you; set numbers with `rw_steward_stock_set(kind="forestry", target=900)` when you want them to stay.
- **Stone or steel base going up**: mining 600; add `allow=["MineableComponentsIndustrial","MineablePlasteel"]` once you have Mining 8+.
- **6+ colonists**: hunting meat 700+, forestry 900, and a second growing zone; meat rots in 2 days without a freezer, so do not raise meat above ~2 days of cooking (a pawn eats 1.6 nutrition/day; 1 meat = 0.05 nutrition, so 3 colonists eat ~100 meat/day).
- **Wealth discipline**: stock counts as wealth. Do not hold 2000 steel "just in case"; raise a target when a build plan needs it, then lower it.
- **Meat -15 mood** (killed innocent animal) hits the hunter: a lower meat target (150) and a rice field beats aggressive hunting in a 3-pawn colony with a fragile mood.

## When to suspend
- **Raid on the map** (`hostile_group` event, `rw_state_threats` non-empty): `rw_steward_stock_set(kind="hunting", suspended=true)` and forestry too if trees are outside the walls. Better: `rw_steward_posture(label="defend", hours=6)` zeros hunting/forestry/foraging/mining targets and pulls Hunting/PlantCutting/Mining priorities down for everyone; it expires by itself. Resume with `suspended=false` or `rw_steward_posture(clear=true)` on `hostile_group_gone`.
- **Toxic fallout / volcanic winter**: suspend forestry, foraging and hunting (pawns outdoors take toxic buildup; animals are toxic to eat); mining is fine if the ore is under roof. Resume when the condition ends (ledger `message`).
- **Manhunter pack or a predator near home**: suspend hunting; `hunt_predators` stays false.
- **Cold snap / heat wave**: forestry and mining keep running; check no pawn is stuck outside without warm clothes.
- A suspended job keeps its target and resumes exactly where it was; a removed job (`rw_steward_stock_remove`) is gone until you `rw_steward_stock_add` it again.

## Production job for meals
The cook bill is the thing the scorer keys on: no bill, no Cooking priority for anyone. `rw_steward_stock_add(kind="production", target=20, allow=["MealSimple"])` binds a bill on the stove/campfire to a target count and keeps it there (do-until-X with the count updated as the colony grows). Set 10 meals per colonist for a 2-day buffer; a fueled stove cooks 2x a campfire. Check `rw_state_bills(thing=<stove>)` once; do not stack duplicate bills (operator tip: the campfire collects dupes).

## Livestock (opt-in)
Only after you tame something: `rw_steward_stock_add(kind="livestock", target=6, allow=["Chicken"])` keeps the herd at the target by designating slaughter on the surplus (oldest and males first) and leaves breeding pairs. Chickens double every ~5.7 days; without a cap they eat the crops. Do not add livestock for pack animals you want to keep (muffalo, alpaca) unless you want wool herds trimmed.

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
- **Posture presets** (`rw_steward_posture(label=, hours=12)`): `defend` (Doctor, Firefighter, Hauling up; Hunting, PlantCutting, Mining, Growing down; outdoor stock targets x0), `build` (Construction +0.5, Mining/PlantCutting/Hauling +0.3, Research/Art down; forestry and mining targets x1.5), `harvest` (Growing, Cooking, Hunting, PlantCutting up; Research/Art down; foraging and hunting targets x1.5, low-food weight x2), `recover` (Doctor +0.6, Cleaning +0.4, Hauling +0.3; own-room and beauty weights x1.5), `normal` = clear (deltas above are approximate; `rw_steward_status.posture` shows the exact ones in force). Custom: `work={"Research":0.4,"Art":-0.8}` deltas -1..1 per WorkTypeDef, `weights={"ConsiderPassions":0.5}`, `targets={"forestry":1.5}`. One posture at a time; a new call replaces the old one; expiry raises `posture_expired`.
- **Global adjustments** (`rw_steward_settings(scorer={"globalWorkAdjustments":{...}})`) are permanent versions of posture work deltas. Use them for the colony's standing shape (a research colony: Research +0.3), postures for the next 12-48 hours.
- **Weights** (`rw_steward_settings(scorer={"ConsiderBestAtDoing":1.0})`): 0 by default, which spreads work; 1.0 makes the best pawn at each skill own it (good from 5 colonists up). `ConsiderLowFood` 1.0, `ConsiderFoodPoisoning` 1.0, `ConsiderPassions` 1.0, `ConsiderBeauty` 1.0, `ConsiderOwnRoom` 1.0, `ConsiderMovementSpeed` 1.0, `ConsiderWeaponRange` 1.0, `ConsiderPlantsBlighted` 1.0, `TicksBetweenActions` 1 (raise to 5 if the game stutters).
- **Manual pawns** (`rw_steward_pawn managed=false` + `rw_ui_set_work`) are the exception for one pawn with one fixed role; hand them back when the reason is gone.

# What a watcher is still for
Reflexes the steward does not own: draft on `hostile_group`, unforbid drop pods, resume suspended jobs on `hostile_group_gone`, call `rw_steward_posture(label="defend")` the moment a raid lands. A watcher that designates trees or sets priorities duplicates the steward and fights it; delete it.
