---
always: false
description: Pull in when a pawn is injured, bleeding, downed, sick (infection, flu,
  plague, malaria), when setting medical policies, assigning a doctor, or deciding
  what medicine to use or grow.
name: medicine-and-health
tags:
- medicine
- health
- infection
- disease
- bleeding
- burns
- fire
- rescue
---

# Medicine and health

## Setup (do this on day 1)
- Doctor: the steward scorer gives Doctor to the highest Medical skill and raises it +0.5 when someone is injured (non-doctors capped at 0.6). During a plague or after a bad raid, `rw_steward_posture(label="recover", hours=24)` (Doctor +0.4). Only if the single medic must not leave the hospital: `rw_steward_pawn(pawn=, managed=false)` then `rw_ui_set_work(priorities={"Doctor":1})`, and hand back after. Pawns incapable of Caring never doctor. Enable self-tend only if nobody else can tend (x0.7 quality).
- Medical policy: the `policies` standing order sets colonists to NormalOrWorse and prisoners and animals to HerbalOrWorse, and never touches a pawn again once you set its care by hand (or it changed outside the order): set it back to NormalOrWorse yourself when the plague or infection is over, or you keep burning good medicine. Intervene per patient: `rw_ui_set_policies(pawn=, medical=Best)` the moment infection or plague appears, `HerbalOrWorse` on a colonist with bruises while industrial medicine is scarce, `NoMeds` on a prisoner you will not recruit.
- Grow healroot (Plant_Healroot) via rw_ui_zone once a grower has Plants 8: 7 grow days, min fertility 0.7, 1 herbal medicine per plant, survives winter. Plant 20+ tiles; one fight can cause half a dozen wounds.

## Medicine tiers
| Medicine | Potency | Max tend quality | Notes |
|---|---|---|---|
| None (doctor care) | 0.3 | 70% | Slow, one wound per tend; use for bruises |
| Herbal (MedicineHerbal) | 0.6 | 70% | Bleeding cuts, flu, cheap surgery |
| Industrial (MedicineIndustrial) | 1.0 | 100% | Infections, plague, surgery; 3 cloth + 1 herbal + 1 neutroamine at a drug lab (Medicine production) |
| Glitterworld (MedicineUltratech) | 1.6 | 130% | Trade only; save for lethal disease or risky surgery |

Tend quality = base (Medicine skill 0: 20%, 6: 80%, 8: 100%, 20: 155%) x potency, +0.1 hospital bed, +0.07 vitals monitor, x0.7 self-tend, randomised 0.75-1.25, capped at the medicine max. Doctor Manipulation and Sight scale it. Cleanliness affects infection chance, not tend quality; light affects tend speed and surgery. Surgery: Medicine 8 with industrial medicine, lit clean room and hospital bed hits the 98% cap; Medicine 11 without the hospital bed.

## Infection (the early-game killer)
- Chance per wound: bites/burns 30%, frostbite 25%, shredding 20%, other bleeding wounds 15%; bruises and lost parts never infect. Tending multiplies the chance by 85% at 0% quality down to 5% at 100%; a clean floored room halves it, sterile tile x0.32, outdoors x1.0. Tend every cut, indoors, promptly.
- Then it is a race: severity +0.84/day untreated, immunity +0.644/day (about 1.5 days), 100% tend slows it by 0.53/day. Untreated it kills in under 1.25 days. A rested, fed pawn needs at least 15% average tend quality, re-tended every 12 hours; herbal with a skill 6-10 doctor works if started within hours. Extreme stage (78%+) means unconsciousness; the Medical emergency alert fires at 80%.

## Burns (the fire-specific killer)
- Burns are the #1 cause of death in fire events. Burn severity: 0.5-1.5 minor (treatable), 2-4 moderate (needs herbal medicine), 5-8 severe (needs industrial medicine, hospital bed), 8+ lethal (torso burns at 8+ are almost always fatal without ultratech medicine).
- **Burns + heatstroke compound:** a pawn in a 1000C room gets both. Heatstroke alone kills in ~1 hour at extreme severity. Burns prevent the pawn from leaving the hot room (they're downed). This is the "death trap" pattern: downed in a hot room, no one can rescue them because all beds are in the fire zone.
- **Prevention beats treatment:** the best burn treatment is not being in the fire zone. Replace wood walls with steel/stone, keep a fire break between kitchen and bedrooms, and ensure at least one bed is OUTSIDE the main building (outdoor sleeping spot or a separate small room).
- **If a fire starts:** undraft all colonists immediately (drafted pawns cannot fight fires; the `fire` order only raises firefighting for an hour and logs the fire, it never undrafts). The `rescue` order carries a colonist downed in the fire zone to a free bed; it fails when every bed is in the hot room (it places a medical sleeping spot only when no bed exists at all). Then place a bed blueprint in safe ground and have a builder construct it while the fire burns out.
- **After the fire:** check all colonists for burns + heatstroke + bleeding. Burns have 30% infection chance. If you have no medicine, the best you can do is keep the patient warm, fed, and rested, immunity will fight it, but severe burns will likely kill.

## Other diseases (tend, feed, bed rest)
| Disease | Severity/day | Immunity/day | Max treatment slowdown | Kills untreated | Notes |
|---|---|---|---|---|---|
| Flu | 0.249 | 0.239 | 0.077 | 4.01 days | Survivable with bed rest alone; tend every 12 h |
| Malaria | 0.370 | 0.314 | 0.232 | 2.70 days | Needs >=24% average tend; lowers blood filtration, so rest matters |
| Plague | 0.666 | 0.522 | 0.363 | 1.5 days | Needs >=15% tend, every 15 h; use industrial medicine |

Immunity gain speed falls when hungry or tired and rises with bed type (ground 1.0, bed 1.07, hospital bed 1.11). Penoxycyline prevents malaria, plague and sleeping sickness.

## Bleeding and blood loss
- Blood loss stages: minor 15%, moderate 30%, severe 45%, extreme 60% (life threatening), death at 100%. Bleeding stops only when tended. Read "bleeding out in X hours" from rw_state_pawn and tend the fastest bleeder first.

## When a colonist is downed
1. The `rescue` standing order does the carrying: the nearest capable colonist gets a Rescue job to a free bed or sleeping spot (a sleeping spot has only 0.7 surgery success; if no bed exists at all it places a medical sleeping spot next to the nearest one), and anyone bleeding out within 6 h gets a doctor via TendPatient when nobody is tending. It keeps running every 300 ticks during a raid: it never uses pawns the combat order drafted, but any undrafted colonist (unarmed, pacifist, child, unmanaged) is fair game and it will path through danger, so if the yard is under fire either `rw_steward_orders_set(id="rescue", enabled=false)` for the fight or issue the rescue yourself with `rw_ui_order` (that pawn is then hands-off for an hour); the combat order runs it once more the moment it releases. `rw_steward_orders` shows `rescue` with its last action; `rw_steward_orders_run(id="rescue")` forces a pass.
2. **Intervene when the order cannot** (`colonist_downed` still on the ledger a few minutes later, `rescue` summary says no bed or no path): check `rw_state_base` for TRAPPED colonists and deconstruct the blocking wall if the room is sealed; if no bed stands in safe temperature, place a bed blueprint in safe ground and have a builder construct it. `rw_ui_order(pawn=<healthy pawn>, at=<downed pawn id>, label="rescue")` by hand only for a specific carrier (the order then leaves that patient to you for an hour).
3. The scorer raises Doctor on its own for the injured; tending and feeding happen in bed. Undraft the doctor if you drafted them.
4. Later build a Hospital bed (Hospital bed research, Construction 8, 40 stuff + 80 steel + components: +0.1 tend, x1.1 surgery, 1.11 immunity), keep the room floored and clean, add sterile tile when steel allows. Any bed in a room with the Hospital role is set to medical by the `beds` order; a bed you toggle by hand stays as you left it for 2 days.

## Prisoners
Capture downed raiders to a prisoner bed (the `beds` order assigns prisoners to free prisoner beds); the same doctor tends them at their own policy (HerbalOrWorse by the `policies` order). Untended prisoners infect and die, so tend anyone you want to recruit.

Sources: Medicine; Herbal medicine; Glitterworld medicine; Doctoring; Infection; Disease; Flu; Plague; Malaria; Immunity Gain Speed; Healroot; Hospital bed; Hediffs/Core/Global/Misc/Blood loss; Rescue; Prisoner; Sleeping spot; Bed