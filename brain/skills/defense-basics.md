---
always: false
description: Pull in when a raid letter arrives, rw_state_threats shows hostiles,
  or when planning walls, traps, turrets, chokepoints, the rally point and draft
  positioning for a small colony. Also pull in when a mech (Scyther, Centipede, Scorcher, Lancer) is
  on the map or sleeping nearby.
name: defense-basics
tags:
- defense
- raid
- traps
- turrets
- drafting
- rally
- mechs
---

# Defense basics

## What a raid costs
Raid points = (Wealth points + Pawn points) x Threat scale x Starting factor x Adaption factor. 1 point buys ~1 combat power; minimum 35 points, cap 10,000.
- Wealth points: 0 at storyteller wealth <= 14,000; 2,400 at 400,000 (~1 point per 161 wealth). Storyteller wealth = items + creatures + half of buildings.
- Pawn points: 15 per colonist at <= 10,000 wealth, up to 140 per colonist at 400,000. Attack-trainable animals add 8% of combat power.
- Starting factor 0.7 for days 0-10, 1.0 from day 40. Adaption factor starts 0.8, 30-day grace period (range 0.4-1.47).
- Threat scale: Adventure story 0.60, Strive to survive 1.00, Blood and dust 1.55, Losing is fun 2.20.
- Combat power: Drifter 35, Tribal archer 45, Warrior 50, Pirate gunner 65, Scyther 150, Centipede 400.
Human raiders flee once 40-70% of their group is downed or after 10-15 hours; mechanoids never flee.

## Raid types
| Letter | Behavior | Response |
|---|---|---|
| Walk in (45%) | Shortest open path to a colonist; walls only bashed if no open path | The combat order holds the rally point; watch, do not touch |
| "Preparing" | Idle near spawn first | The order already drafted; snipe with one pawn if they idle in rifle range |
| Drop pods (30%) | Land near a colonist (10% mid-base); ~9 s before pods open | Pods inside the base: the order switches to attack-nearest; add `rw_ui_attack` focus fire on the first raider out |
| Sappers / Breachers | Dig or smash walls straight toward an assigned bed; sappers avoid turret sight; smaller raid | Intervene: the rally point faces the wrong way. `rw_ui_goto` the shooters to the breach and hit them at the wall; do not wait in the killbox |
| Siege | 2 mortars outside; assault after 1.5-3 days, or 8% chance per hit taken | Attack the camp early, or wound one to trigger the assault into your defenses |

## The rally point and the combat order
The `combat` standing order (`rw_steward_orders`) is the colony's draft reflex. When any hostile has a path to the home area, or a raid/siege/mech-cluster/manhunter event lands, it drafts every colonist who holds a ranged or melee weapon (skips downed, prisoners, children, pacifists, anyone under 30% health or in a mental break, and pawns you took unmanaged), sends each to its own cell inside the **rally rect** (cover-aware: cells next to walls and sandbags first), restricts the non-fighters to the Home area, and re-issues positions to anyone who wandered every 250 ticks. Once no hostile is left for 600 ticks it undrafts, restores allowed areas and runs `rescue` once. If a hostile reaches the base or comes within 5 cells of the rally centre it switches every fighter to attack-nearest.

**Set the rally point on day 1-2, the moment the first walls stand:** `rw_steward_orders_rally(rect=[x,z,w,h])`, a 3x2 to 4x3 rect just inside the single door, behind the wall corners, out of the trap lane, on the hospital side of the base so the downed are carried a short way. `rw_steward_orders_rally()` reads it, `rw_steward_orders_rally(clear=true)` removes it; move it whenever the door moves. Without one the order still drafts, but it parks the fighters around the base centre in the open, which is how colonists die in the yard. The situation packet says `rally: none` until you set it.

**What it does not do:** no kiting, no focus fire, no turret management (rearm, power, hold fire), no sorties, no mortars, no retreat into the hospital, nothing for animals, nothing against a berserk colonist or a manhunter already inside a closed base. It targets only hostiles and never uses dev tools.

**A manhunter or hostile chasing one colonist far from base is your job, not the order's**, and "it's N cells from home" is the wrong yardstick: the order only drafts when a hostile has a path *to the home area*, so a lone colonist under attack out in the wilderness gets no automatic help at all, no matter how far away the base is. Judge urgency by the danger to that colonist (bleeding, health, whether they're armed, whether they can outrun it), not by distance to the base. If they can't survive alone, draft a colonist and send them to intercept (`rw_ui_draft` + `rw_ui_goto`) or accept the loss deliberately, and set a short wake (well under an hour) rather than a multi-hour sleep while it plays out unwatched. When RimBridge reports a "Medical treatment needed" or similar High-priority alert, that pawn is hurt now, check on them at your next wake rather than waiting for it to escalate to Critical.

**Never send your last able colonist far from base to rescue someone while the thing that downed them is still loose and could reach the base.** Check `rw_state_threats` before committing to a rescue: if the hostile that caused this is still alive and has a path home, defending the base comes first, undrafting your only defender to walk 80+ cells away leaves nobody to fight if it arrives while they're gone, and if the rescuer goes down too you have converted one casualty into a colony-ending one. With a single healthy colonist left, a distant multi-cell rescue is usually the wrong call entirely: shelter behind a door, hold position near home, or accept the loss and keep your last colonist alive, rather than gambling the whole colony on a long walk through open ground.

**When to intervene** (and only then): breachers and sappers coming through a wall the rally does not cover; drop pods inside the walls; a mech cluster (sleeping mechs are not a raid until they wake, see below); a siege you want to sortie against; a fire during the fight (drafted pawns cannot fight fire: undraft two). `rw_ui_draft`/`rw_ui_goto`/`rw_ui_attack` on a pawn makes the order leave that pawn alone for ~2500 ticks (an hour), so an override sticks; `position_shooters(cell=)` does the same for several. Do not draft pawns yourself otherwise: a hand-drafted pawn is a pawn the order will not undraft when the raid ends, and a pawn you drafted for a chore keeps standing there. `rw_steward_orders_explain(id="combat")` lists who is hands-off and for how long.

## Structures
- Walls: 75% cover, block line of fire, pawns lean out at corners. Raiders take the quickest unobstructed route, so a perimeter with exactly ONE 1-wide entrance (bent so they cannot shoot in) turns every raid into a chokepoint fight. Stone is best; wood and steel burn. rw_ui_build def Wall.
- Sandbags/barricades: 55% cover, do not block line of fire, 5 cloth/leather or 5 blocks. Stone chunks: free 50%; trees 25%; bushes 20%. Cover is 100% effective at <15 degrees off-axis, 0% past 65 degrees, 33% at point-blank.
- A lone door is high cover; hold it open to fire through.
- Spike trap: 45 wood/stone/steel, single use, 5 stab hits from 100 base damage. Not placeable adjacent to another trap; **colonists CAN trigger them, raiders cannot see them.** Use a 2-wide entrance: traps in one lane, fences in the other so colonists take the fence lane.
- Mini-turret: Gun turrets research; 30 stuff + 70 steel + 3 components, 80 W, 60 shots per 80 steel reload. 12 damage 2-round burst, range 28.9, ~Shooting 8. 50% chance to explode (50 bomb, 3.9 radius) below 20% HP: space turrets 4+ tiles apart, off your firing line. Dead in a solar flare.

## Spike trap placement, the self-trigger trap (episode 3 lesson)
**Colonists trigger their own spike traps.** In episode 3, Kena was downed by a spike trap in the south approach lane [117,116], the same lane she walked through to exit the barracks. The traps were meant for raiders but the colonist exit path went straight through them.

**Rule:** Place spike traps in the raider approach lane ONLY, offset from the colonist exit path. If the entrance is 2-wide: traps in the raider lane, a clear fence lane for colonists. If the entrance is 1-wide (a single door), put traps OUTSIDE the door on the raider approach side, not inside the barracks where colonists walk. A downed colonist in a spike trap is a medical emergency that wastes your doctor's time and can kill them if bleeding is severe.

## Sleeping mechs, the warning window (episode 2 lesson)
When `rw_state_threats` shows a mech with `LordJob_SleepThenAssaultColony` (or any mech within ~150 cells of home):
1. **This is a countdown, not a raid.** The mech will wake and assault with no warning letter. You have hours, not days.
2. **Assess immediately:** `rw_state_threats` → note the mech type, count, and distance. Scorcher (flameblaster) + Lancer (charge lance) = 2 mechs, ~300+ combat power combined. A 3-colonist colony cannot win this head-on.
3. **Build defenses in the window:**
   - If you have turrets: position them at the approach lane, fire-at-will on.
   - If you have steel: build sandbags (5 steel each) or a wall line at the chokepoint.
   - If you have wood: spike traps in the approach lane (5+ traps).
   - If you have cloth: sandbags (5 cloth each).
4. **Put the rally point at the chokepoint** (`rw_steward_orders_rally`) BEFORE the mechs wake; the combat order drafts the shooters there the moment they do. Draft by hand only if you want them in position early (a hand-drafted pawn is hands-off to the order for an hour).
5. **If the odds are hopeless** (2+ mechs vs 2-3 colonists, no turrets, no walls): consider whether the colony is already lost. Do not waste steps on a lost cause. Note it in the notebook and end the episode honestly.
6. **Mechs never flee.** They do not retreat at 40% casualties. Plan for a total engagement or a total loss.

## No power = no turrets = death (episode 3 lesson)
**The #1 cause of loss in episode 3: no power grid, therefore no turrets, therefore no defense against the mech assault.** With 22 colonists the threat points were 500 by day 1, meaning a 500-point raid (≈ 10-12 pirates with guns) was coming within days. Without turrets, the colony had to rely on manual drafting of 22 pawns, which is impossible to coordinate.

**Rule: build a wood-fired generator + battery + 2 mini-turrets BEFORE the first raid.** This is a day-0 priority, not a day-10 luxury. The generator costs 100 steel + 2 components; each turret costs 30 stuff + 70 steel + 3 components; the battery costs 70 steel + 2 components. Total ≈ 400 steel + 8 components. Crashlanded loot has ~1,450 steel. If you do not have turrets by the time threat points exceed 100, you are already in danger.

**In god mode / sandbox:** spawn turrets directly with `rw_dev_spawn` (def="Turret_MiniTurret") at the approach lane. This is the fastest way to get defense in a sandbox game. Note: the defName is `Turret_MiniTurret`, not `Turret_Gun`.

## Day 8-10 raid-prep checklist (3-colonist colony, walled barracks)
By day 8 you should have:
1. **Walled barracks** with one door (the chokepoint). Steel or stone walls preferred; wood is a fire risk.
2. **3 spike traps** in the raider approach lane (OUTSIDE the door, not in the colonist exit path).
3. **All 3 colonists armed and equipped:** best Shooting pawn holds the bolt-action rifle or revolver; second shooter holds the other ranged weapon; the third holds a melee weapon (plasteel knife is fine).
4. **Work priorities set:** the best shooter has Hunting 2 (so they can hunt if needed); the doctor has Doctor 1; the builder has Construction 1.
5. **Cooking bill running** (Forever CookMealSimple on campfire or stove). Food days >= 3.
6. **No forbidden items** in the approach lane (forbidden items block paths and cause pathing errors).
7. **Threat points read:** `rw_state_threats` shows the current threat level. At 35 points, expect a 1-2 raider raid (35-70 CP) within 2-3 days.
8. **Rally point set:** `rw_steward_orders_rally(rect=)` over the door corners (1 tile inside, 1 tile apart); the combat order spreads the fighters over it. Fire at will on all shooters.
9. **Turrets:** at least 1 mini-turret at the approach lane (requires power grid). If no power yet, build the generator + battery first.

**On the raid letter:**
1. `rw_state_threats` → note raider type, count, distance, and approach direction.
2. **The combat order has already drafted the armed colonists to the rally rect** (`rw_steward_orders` shows `combat` acting on N). Only if the raid comes from a side the rally does not cover: `position_shooters(cell=[door_x, door_z])`, one call instead of N `rw_ui_goto` calls, and those pawns are yours for the next hour.
3. `rw_ui_attack` to focus the raider with a gun; that pawn stays hands-off to the order for an hour, so undraft it yourself after.
4. `rw_game_speed(speed=1)`, slow the fight down for precise orders.
5. After the raid: the order undrafts everyone it drafted, restores areas and runs `rescue`. The `unforbid` and `corpses` orders take the loot and the bodies; you decide what to smelt or gift.

## Turret defName
The correct defName for the mini-turret is `Turret_MiniTurret` (not `Turret_Gun`). Use `rw_defs_search(query="turret")` to verify.