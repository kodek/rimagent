---
name: defense-basics
description: Pull in when a raid letter arrives, rw_state_threats shows hostiles, or when planning walls, traps, turrets, chokepoints and draft positioning for a small colony.
tags: [defense, raids, combat, killbox, turrets, cover]
always: false
---
# Defense basics

## What a raid will cost you
Raid points = (Wealth points + Pawn points) x Threat scale x Starting factor x Adaption factor. Roughly 1 point buys 1 combat power of raider. Minimum raid is 35 points, cap 10,000.
- Wealth points: 0 at storyteller wealth <= 14,000; 2,400 at 400,000 (about 1 point per 161 wealth in between). Storyteller wealth = items + creatures + 0.5 x buildings.
- Pawn points: 15 per colonist at <= 10,000 wealth, rising to 140 per colonist at 400,000. Attack-trainable animals add 8% of their combat power.
- Starting factor: 0.7 for the first 10 days, ramps to 1.0 at day 40. Adaption factor starts 0.8, grace period 30 days before it climbs (range 0.4 to 1.47).
- Threat scale: Adventure story 0.60, Strive to survive 1.00, Blood and dust 1.55, Losing is fun 2.20.
- Example combat powers: Drifter 35, Tribal archer 45, Warrior 50, Scavenger gunner 50, Pirate gunner 65, Berserker 65, Scyther 150, Centipede 400. A 3-colonist day-8 colony on Strive is often ~45 x 0.7 x 0.8 = 25 (floored to 35): one or two raiders.
Human raiders flee once 40-70% of their group is downed/dead, or after 10-15 hours of attacking. Mechanoids never flee.

## Raid types and what changes
| Letter says | Behavior | Response |
|---|---|---|
| Walk in from edge (45%), immediate | Beeline for colonists via shortest open path; will not bash walls if any open path exists | Fight at your chokepoint |
| Preparation / "will attack soon" | Stand near spawn for a while first | Free time to draft, or snipe them while they idle |
| Drop pods (30%) | Land near a colonist (10% chance center-of-base); ~9 s before pods open | Draft every armed pawn nearby; melee them as they emerge; evacuate non-fighters |
| Sappers | Best miner digs/blasts to an assigned bed; avoid turret line of sight; smaller raid | Attack them at the wall before they finish; do not wait in the killbox |
| Breachers | Tribal breach axes / frag grenadiers / Termites smash your walls in a straight line to a bed | Same as sappers: sortie and hit them while they hammer the wall |
| Siege | Camp outside, build 2 mortars, assault after 1.5-3 days; 8% chance to charge each time one takes damage | Hit the camp early or snipe one to trigger the assault into your defenses |

## Structures that matter
- Walls: 75% cover, block line of fire, pawns lean out at corners. Raiders use the quickest unobstructed path, so a perimeter wall with exactly ONE open entrance (a 1-wide gap with a bend so they cannot fire in from outside) turns every raid into a chokepoint fight. Build stone when possible (wood and steel walls burn). rw_ui_build def Wall stuff <blocks>.
- Sandbags/barricades: 55% cover, do not block line of fire, 5 cloth/leather (sandbags) or 5 blocks/wood (barricade). Stone chunks are free 50% cover; trees 25%, bushes 20%. Cover is 100% effective at <15 degrees off-axis, 0% beyond 65 degrees, and only 33% at point-blank. Combine wall corner plus sandbag gap for 75%+.
- A lone door counts as high cover; hold it open so pawns can fire through it.
- Spike trap (def TrapSpike): 45 wood/stone/steel, single use, 5 stab attacks off a 100 base damage. Traps cannot be adjacent to each other, colonists CAN step on them, and raiders cannot see them. Put them in a 2-wide entrance corridor: traps in one lane, fences in the other so your pawns take the fence lane. Auto-rearm makes a blueprint after each trigger.
- Mini-turret: needs Gun turrets research; 30 stuff + 70 steel + 3 components, 80 W power, 60 shots then 80 steel reload. 12 damage 2-round burst, range 28.9, ~Shooting 8. 50% chance to explode (50 bomb dmg, 3.9 radius) below 20% HP, so keep turrets 4+ tiles apart and away from your firing line. Useful as decoys and in killboxes; useless in a solar flare.

## Drafting checklist
1. On the raid letter: rw_state_threats, then rw_ui_draft everyone violence-capable BEFORE the enemy is in range. Drafted pawns ignore needs, so feed and rest them first if the raid is "preparing".
2. rw_ui_goto each shooter to a wall corner or sandbag facing the approach, 1 tile apart to reduce collateral; melee pawns stand just outside the door/gap (not in it), up to 3 of them, so each raider is forced into a 1v3.
3. Fire at will handles targeting; use rw_ui_attack to focus a grenadier, rocketeer or the closest melee rusher. Do not chase fleeing raiders into the open.
4. Drag wounded pawns out of the line of fire immediately; a bleeding pawn has ~2 hours. Undraft when the raid flees so pawns eat, sleep and tend.
5. After: rw_ui_designate haul loot, strip/capture downed raiders, rebuild traps, repair walls.

## First raid with 3 colonists
Expect 1-2 poorly armed raiders. Before day 10 build: a walled bedroom cluster with one door, 3-5 wood spike traps in the approach lane, one stone-chunk or sandbag line, and give the best Shooting pawn the best gun. Fight from the doorway, keep the other two beside a wall corner, and never fight in the open field.

Sources: Raid points; Raider; Pirates/Pawns; Tribes/Pawns; Defense tactics; Defense structures; Cover; Sandbags; Spike trap; Mini-turret; Drafting
