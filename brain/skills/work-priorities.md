---
always: false
description: Pull in when setting or auditing colonist work priorities (rw_ui_set_work),
  when a new pawn joins, or when jobs are not getting done (nobody cooking, hauling,
  researching).
name: work-priorities
tags:
- work
- priorities
- roles
- steward
---

# Work priorities

## How the system works
- Manual priorities: 1 = highest, 4 = lowest, 0 = never. rw_ui_set_work {pawn, priorities: {WorkTypeDef: 0-4}} enables manual mode. Call rw_defs_work_types first: it returns every WorkTypeDef in game order with what it covers, and those defNames are what rw_ui_set_work expects.
- A pawn does all available priority-1 work before any priority 2, and within one priority works left to right in list order. Hauling at 1 means hauling every item on the map first, so never put Hauling or Cleaning at 1.
- Pawns only work inside their allowed area (rw_ui_set_policies area).

## Work types in game order (base game, with the skill each uses)
Firefight (none), Patient (none), Doctor (Medical), Bed rest (none), Basic (none), Warden (Social), Handle (Animals), Cook (Cooking), Hunt (Shooting and Animals, needs a ranged weapon), Construct (Construction), Grow (Plants), Mine (Mining), Plant cut (Plants), Smith (Crafting), Tailor (Crafting), Art (Artistic), Craft (Crafting; stonecutting and smelting use no skill), Haul (none), Clean (none), Research (Intellectual). Childcare, Fish and Dark study exist only with Biotech, Odyssey and Anomaly. Verified defNames (rw_defs_work_types, in game order): Firefighter, Patient, Doctor, PatientBedRest, BasicWorker, Warden, Handling, Cooking, Hunting, Construction, Growing, Mining, PlantCutting, Smithing, Tailoring, Art, Crafting, Hauling, Cleaning, Research (Childcare, Fishing, DarkStudy also appear when their DLC is loaded).

## Skills and what they gate early
- Plants: sow/harvest speed; healroot needs 8, devilstrand 10. Cooking: 9 minimises food poisoning, 10 maxes butcher yield. Construction: speed 50% + 15% per level, no botches from 8; solar needs 6, hospital bed 8. Medical: tend quality 20% at 0, 100% at 8. Intellectual: research speed 8% + 11.5% per level. Shooting: per-tile accuracy 89% at 0, 97% at 10, compounding with range. Mining: speed and ore yield. Crafting: item quality and bill minimums only. Social: recruiting, trade prices. Animals: taming, less hunting revenge. Artistic: ignore early.
- Passion: none = 35% XP, one flame = 100% XP and +8 mood while working, two flames = 150% XP and +14 mood. Prefer passionate pawns at equal skill.
- Skills above 10 decay (30 XP/day at 10, 3600 at 20). Three level-9 generalists beat one level-16 specialist except for quality crafting.
- Incapable (Bio tab): Caring blocks Doctor; Violent blocks Hunt, Warden and combat; Dumb labor blocks Haul and Clean; Skilled labor blocks Cook, Construct, Mine, Grow, Craft; Intellectual blocks Research; Animals blocks Handle; Social blocks Warden and trading. Skill 0 is slow but allowed; incapable is never. Check rw_state_pawn before assigning.

## Default matrix for 3 Crashlanded colonists
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

Rules: Firefighter, Patient and PatientBedRest stay at 1 for everyone. Only the pawn holding the bolt-action rifle hunts; without a ranged weapon Hunting never runs. The Medical pawn keeps Doctor 1 even while researching. Keep two pawns at 3 on Cooking and Growing so a downed specialist does not stop food.

## Steward-managed colonies (the default here)
The steward's scorer sets priorities from skills, passions, health and colony need, and **hand-editing a pawn's priorities with `ui.set_work` ejects that pawn from management for good**. Bias the scorer instead, don't override it:
- Posture: `steward.posture(label="warmup", hours=24, work={"Construction": 0.4, "Cooking": 0.5}, targets={"forestry": 1.5})` — `work` is -1..1 per WorkTypeDef, `targets` multiplies stock-job targets. It expires by itself.
- Stock jobs: raise/lower a target, or `steward.stock.run(kind=...)` to force a pass now (forestry/mining/foraging/hunting).
- **Known artifact:** with unhauled items lying around, the scorer puts **Hauling 1 on every pawn**, and then Cooking/Construction/Research starve. Symptoms: 0 meals while raw food sits in the stockpile, or a blueprint count that has not moved for a day. Fix with a posture (e.g. `work={"Hauling": -0.5, "Cooking": 0.5, "Construction": 0.4}`), not by hand.
- Only take one pawn manual for a real blocker (e.g. literally nobody else can cook): `steward.pawn managed=false` + `ui.set_work`, note it, hand back with `managed=true`.
- Audit order: raw food but no meals -> check `state.bills` on the stove/campfire (a missing CookMealSimple bill is the usual cause) BEFORE blaming priorities; then check the best cook isn't drowned in Hauling.

## Audit triggers
- Raw food but no meals -> nobody has Cooking, or the stove lacks a bill (rw_ui_add_bill).
- Blueprints untouched for a day -> Construction 0 everywhere or materials forbidden (rw_ui_designate unforbid); also check the steward is not burying Construction under Hauling.
- Items rotting outside or filth spreading -> Hauling or Cleaning 2 on one pawn temporarily.
- New recruit -> rw_state_pawn, apply the matrix, move their best passion skill to 1 or 2.

Sources: Work; Skills; Doctoring; Healroot; Devilstrand (plant); Solar generator; Hospital bed; Research Speed