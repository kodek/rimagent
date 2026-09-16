---
always: false
description: Pull in when the Steward block shows an unmanaged pawn or a work type nobody
  does, when a new pawn joins, when jobs are not getting done (nobody cooking, hauling,
  researching), or before overriding the steward with rw_ui_set_work. Explains how the
  steward scores work and when a manual override is worth it.
name: work-priorities
tags:
- work
- priorities
- skills
- passion
- steward
- early-game
---

# Work priorities

## Who sets them
The **steward scorer** (vendored Free Will, C#, inside RimBridge) sets every managed colonist's priorities every few ticks. You do not. Your levers, in order: `rw_steward_posture` (colony-wide deltas, timed), `rw_steward_settings` (weights), `rw_steward_pawn managed=false` + `rw_ui_set_work` (one pawn, manual). Read `rw_steward_status` first; it lists each pawn's top 3 work types with the reasons. Read `rw_steward_explain(pawn=)` before touching anything.

## How the scorer decides (numbers)
- Every work type gets a score 0..1 per pawn, recomputed on a cadence (`TicksBetweenActions`, default 1 evaluation per tick, so a full pass over 3 pawns x 20 work types takes ~60 ticks = 1 in-game minute).
- Score -> priority: > 0.80 = 1, 0.61-0.80 = 2, 0.41-0.60 = 3, 0.21-0.40 = 4, <= 0.20 = 0 (off). Firefighter, Patient, BedRest and Basic are "always do": never below 4.
- Base 0.2 for anything the pawn can do. Then adds: relevant skill vs the colony's best (best at doing x1.5 when `ConsiderBestAtDoing` > 0; default 0), minor passion +0.25, major +0.5, inspiration +0.4, currently doing it x1.8, low food +0.4-ish on Cooking/Growing/Hunting/PlantCutting (`ConsiderLowFood` 1.0), food poisoning risk pushes Cooking to the skilled cook (`ConsiderFoodPoisoning` 1.0), injured colonist +0.5 on Doctor for the best medic (non-doctors capped at 0.6), fire in home area -0.2 on everything but Firefighter, colonist unburied / animals roaming +0.4 on Hauling/Handling, refueling 0.35/0.20, warm clothes needed +0.2 on Tailoring, deteriorating items x2 on Hauling, own room dirty x2 on Cleaning (`ConsiderOwnRoom` 1.0), movement speed vs 4.6 c/s scales Hauling, carrying capacity vs 75 too.
- Hunting: 0 without a ranged weapon (`ConsiderHasHuntingWeapon`), 0 for brawlers (`ConsiderBrawlersNotHunting`), weapon range vs the bolt-action's 37 (`ConsiderWeaponRange` 1.0).
- Colony policy: `globalWorkAdjustments` (steward.settings scorer) + posture delta (steward.posture work) clamped to -1..1 per work type is added last. -1 turns a work type off for everyone; +0.5 moves it up about two priority steps.
- Incapable (Bio tab) is always 0; the scorer cannot override it and neither can you.
Read the reasons, not the numbers: `rw_steward_explain(pawn="Jen", work="Cooking")` -> `[{work, priority, score, reasons:[{label, delta}]}]`.

## When to override, and how
Override only when the scorer is provably wrong for your plan, and prefer the widest lever that fixes it:
1. **Everyone should shift for a while** (harvest before frost, build before winter, raid coming): `rw_steward_posture(label="build", hours=12)` or custom deltas `rw_steward_posture(label="frost", hours=8, work={"PlantCutting":0.6,"Growing":0.6,"Research":-0.5})`. It expires by itself (`posture_expired` ledger event).
2. **The colony as a whole undervalues something** (nobody researches for days): `rw_steward_settings(scorer={"globalWorkAdjustments":{"Research":0.4}})`. Persistent; note it in the notebook.
3. **One pawn must do one job no matter what** (the only medic must stay Doctor 1 during a plague; the shooter must never hunt during a raid window): `rw_steward_pawn(pawn="Sparky", managed=false)` then `rw_ui_set_work(pawn="Sparky", priorities={...})`. `rw_ui_set_work` alone also unmanages the pawn and returns `steward_managed: false`; either way, that pawn is now yours until `rw_steward_pawn(pawn="Sparky", managed=true)`. Hand the pawn back the moment the reason is gone; an unmanaged pawn with everything at 0 is listed under `problems`.
Never set priorities on a managed pawn and expect them to hold: the next scorer pass overwrites them.

## Work types in game order (base game, with the skill each uses)
Firefight (none), Patient (none), Doctor (Medical), Bed rest (none), Basic (none), Warden (Social), Handle (Animals), Cook (Cooking), Hunt (Shooting and Animals, needs a ranged weapon), Construct (Construction), Grow (Plants), Mine (Mining), Plant cut (Plants), Smith (Crafting), Tailor (Crafting), Art (Artistic), Craft (Crafting; stonecutting and smelting use no skill), Haul (none), Clean (none), Research (Intellectual). Childcare, Fish and Dark study exist only with Biotech, Odyssey and Anomaly.

## Verified defNames (rw_defs_work_types, in game order)
These are the EXACT strings for `rw_ui_set_work`, `rw_steward_explain(work=)`, `rw_steward_posture(work={...})` and `globalWorkAdjustments`. Any other name errors:

| defName | Work |
|---|---|
| Firefighter | Firefight |
| Patient | Patient |
| Doctor | Doctor |
| PatientBedRest | Bed rest |
| BasicWorker | Basic |
| Warden | Warden |
| Handling | Handle |
| Cooking | Cook |
| Hunting | Hunt |
| Construction | Construct |
| Growing | Grow |
| Mining | Mine |
| PlantCutting | Plant cut |
| Smithing | Smith |
| Tailoring | Tailor |
| Art | Art |
| Crafting | Craft |
| Hauling | Haul |
| Cleaning | Clean |
| Research | Research |

**Common wrong names that cause errors (do NOT use these):**
- "Misc" → does not exist
- "Cutting" → should be "PlantCutting"
- "Fueling" → does not exist (fueling is automatic)
- "Researching" → should be "Research"
- "Building" → should be "Construction"
- "Cooking" is correct (not "Cook")
- "Hunting" is correct (not "Hunt")
- "Growing" is correct (not "Grow")
- "Hauling" is correct (not "Haul")

When in doubt, call `rw_defs_work_types` first and use the exact defName from the result.

## Skills and what they gate early
- Plants: sow/harvest speed; healroot needs 8, devilstrand 10. Cooking: 9 minimises food poisoning, 10 maxes butcher yield. Construction: speed 50% + 15% per level, no botches from 8; solar needs 6, hospital bed 8. Medical: tend quality 20% at 0, 100% at 8. Intellectual: research speed 8% + 11.5% per level. Shooting: per-tile accuracy 89% at 0, 97% at 10, compounding with range. Mining: speed and ore yield. Crafting: item quality and bill minimums only. Social: recruiting, trade prices. Animals: taming, less hunting revenge. Artistic: ignore early.
- Passion: none = 35% XP, one flame = 100% XP and +8 mood while working, two flames = 150% XP and +14 mood. The scorer already prefers passionate pawns (+0.25 / +0.5).
- Skills above 10 decay (30 XP/day at 10, 3600 at 20). Three level-9 generalists beat one level-16 specialist except for quality crafting.
- Incapable (Bio tab): Caring blocks Doctor; Violent blocks Hunt, Warden and combat; Dumb labor blocks Haul and Clean; Skilled labor blocks Cook, Construct, Mine, Grow, Craft; Intellectual blocks Research; Animals blocks Handle; Social blocks Warden and trading. Skill 0 is slow but allowed; incapable is never. Check rw_state_pawn before taking a pawn manual.

## Manual matrix (only for a pawn you took out of steward management)
Pick roles by top skills and passions, then apply:

| Work | Everyone | Grower/Cook | Builder/Miner | Doctor/Researcher |
|---|---|---|---|---|
| Firefighter, Patient, PatientBedRest | 1 | | | |
| Doctor | 3 (backup) | | | 1 |
| BasicWorker | 2 | | | |
| Cooking | 3 | 1 | | |
| Growing | 3 | 1 | | |
| Construction | 3 | | 1 | |
| Mining | 3 | | 2 | |
| PlantCutting | 3 | 2 | | |
| Hunting | 0 | | | 2 only for the best shooter holding the rifle |
| Warden, Handling | 0 until a prisoner or pet exists, then 3 on the Social/Animals pawn | | | |
| Crafting, Smithing, Tailoring, Art | 0 | | 3 | |
| Research | 0 | | | 2 |
| Hauling, Cleaning | 3-4 (everyone) | | | |

Rules: Firefighter, Patient and PatientBedRest stay at 1 for everyone. Only the pawn holding the bolt-action rifle hunts; without a ranged weapon Hunting never runs. The Medical pawn keeps Doctor 1 even while researching. Hauling at 1 means hauling every item on the map first, so never put Hauling or Cleaning at 1. Pawns only work inside their allowed area (rw_ui_set_policies area).

## Audit triggers
- Raw food but no meals -> the stove lacks a bill (rw_ui_add_bill) or a `production` stock job for meals is missing (see manager-patterns); the scorer only gives Cooking to a pawn when there is a bill to work.
- Blueprints untouched for a day -> materials forbidden (rw_ui_designate unforbid), unreachable, or `rw_steward_explain(work="Construction")` shows every builder at 0 (incapable). Posture `build` for 12 h if it is simply outscored.
- Items rotting outside or filth spreading -> the scorer already raises Hauling for deteriorating items; if not, check the pawn's allowed area and `ConsiderMovementSpeed`.
- New recruit -> managed by default; `rw_steward_status` after ~1 in-game hour shows their top 3. Only intervene if they land on something dangerous (Hunting with a knife is impossible; the scorer handles it).
- `problems` lists "unmanaged pawn with everything disabled" -> `rw_steward_pawn(managed=true)` or set priorities yourself.

Sources: Work; Skills; Doctoring; Healroot; Devilstrand (plant); Solar generator; Hospital bed; Research Speed; Free Will (paul-freeman/rimworld-freewill) scorer constants
