---
always: false
description: Pull in when setting or auditing colonist work priorities (rw_ui_set_work),
  when a new pawn joins, or when jobs are not getting done (nobody cooking, hauling,
  researching).
name: work-priorities
tags:
- work
- priorities
- skills
- passion
- early-game
---

# Work priorities

## How the system works
- Manual priorities: 1 = highest, 4 = lowest, 0 = never. rw_ui_set_work {pawn, priorities: {WorkTypeDef: 0-4}} enables manual mode. Call rw_defs_work_types first: it returns every WorkTypeDef in game order with what it covers, and those defNames are what rw_ui_set_work expects.
- A pawn does all available priority-1 work before any priority 2, and within one priority works left to right in list order. Hauling at 1 means hauling every item on the map first, so never put Hauling or Cleaning at 1.
- Pawns only work inside their allowed area (rw_ui_set_policies area).

## Work types in game order (base game, with the skill each uses)
Firefight (none), Patient (none), Doctor (Medical), Bed rest (none), Basic (none), Warden (Social), Handle (Animals), Cook (Cooking), Hunt (Shooting and Animals, needs a ranged weapon), Construct (Construction), Grow (Plants), Mine (Mining), Plant cut (Plants), Smith (Crafting), Tailor (Crafting), Art (Artistic), Craft (Crafting; stonecutting and smmelting use no skill), Haul (none), Clean (none), Research (Intellectual). Childcare, Fish and Dark study exist only with Biotech, Odyssey and Anomaly.

## Verified defNames (rw_defs_work_types, in game order)
These are the EXACT strings to pass to rw_ui_set_work. Using any other name causes an error:

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

## Audit triggers
- Raw food but no meals -> nobody has Cooking, or the stove lacks a bill (rw_ui_add_bill).
- Blueprints untouched for a day -> Construction 0 everywhere or materials forbidden (rw_ui_designate unforbid).
- Items rotting outside or filth spreading -> Hauling or Cleaning 2 on one pawn temporarily.
- New recruit -> rw_state_pawn, apply the matrix, move their best passion skill to 1 or 2.

Sources: Work; Skills; Doctoring; Healroot; Devilstrand (plant); Solar generator; Hospital bed; Research Speed