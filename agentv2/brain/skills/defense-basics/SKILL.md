---
name: defense-basics
description: Pull in when a raid letter arrives, rw_state_threats shows hostiles, or when planning walls, traps, turrets, chokepoints and draft positioning for a small colony.
metadata:
  wake-on: "hostile_group, raid, raider, siege, sapper, breach, drop pod, mechanoid, danger"
---
# Defense basics

## What a raid costs
Raid points = (Wealth points + Pawn points) x Threat scale x Starting factor x Adaption factor. 1 point buys ~1 combat power; minimum 35 points, cap 10,000.
- Wealth points: 0 at storyteller wealth <= 14,000; 2,400 at 400,000 (~1 point per 161 wealth). Storyteller wealth = items + creatures + half of buildings.
- Pawn points: 15 per colonist at <= 10,000 wealth, up to 140 per colonist at 400,000. Attack-trainable animals add 8% of their combat power.
- Starting factor 0.7 for days 0-10, 1.0 from day 40. Adaption factor starts 0.8, 30-day grace period (range 0.4-1.47).
- Threat scale: Adventure story 0.60, Strive to survive 1.00, Blood and dust 1.55, Losing is fun 2.20.
- Combat power: Drifter 35, Tribal archer 45, Warrior 50, Pirate gunner 65, Scyther 150, Centipede 400.
Human raiders flee once 40-70% of their group is downed or after 10-15 hours; mechanoids never flee.

## Raid types
| Letter | Behavior | Response |
|---|---|---|
| Walk in (45%) | Shortest open path to a colonist; walls only bashed if no open path | Fight at your chokepoint |
| "Preparing" | Idle near spawn first | Draft now, or snipe them |
| Drop pods (30%) | Land near a colonist (10% mid-base); ~9 s before pods open | Draft all armed pawns nearby, melee them as they emerge |
| Sappers / Breachers | Dig or smash walls straight toward an assigned bed; sappers avoid turret sight; smaller raid | Sortie and hit them at the wall; do not wait in the killbox |
| Siege | 2 mortars outside; assault after 1.5-3 days, or 8% chance per hit taken | Attack the camp early, or wound one to trigger the assault into your defenses |

## Structures
- Walls: 75% cover, block line of fire, pawns lean out at corners. Raiders take the quickest unobstructed route, so a perimeter with exactly ONE 1-wide entrance (bent so they cannot shoot in) turns every raid into a chokepoint fight. Stone is best; wood and steel burn. rw_ui_build def Wall.
- Sandbags/barricades: 55% cover, do not block line of fire, 5 cloth/leather or 5 blocks. Stone chunks: free 50%; trees 25%; bushes 20%. Cover is 100% effective at <15 degrees off-axis, 0% past 65 degrees, 33% at point-blank.
- A lone door is high cover; hold it open to fire through.
- Spike trap: 45 wood/stone/steel, single use, 5 stab hits from 100 base damage. Not placeable adjacent to another trap; colonists CAN trigger them, raiders cannot see them. Use a 2-wide entrance: traps in one lane, fences in the other so colonists take the fence lane.
- Mini-turret: Gun turrets research; 30 stuff + 70 steel + 3 components, 80 W, 60 shots per 80 steel reload. 12 damage 2-round burst, range 28.9, ~Shooting 8. 50% chance to explode (50 bomb, 3.9 radius) below 20% HP: space turrets 4+ tiles apart, off your firing line. Dead in a solar flare.

## Drafting checklist
1. On the letter: rw_state_threats, then rw_ui_draft every violence-capable pawn BEFORE enemies are in range. Drafted pawns ignore needs, so feed and rest them first if time allows.
2. rw_ui_goto shooters to wall corners or sandbags facing the approach, 1 tile apart. Up to 3 melee pawns stand just outside the door gap (not in it) to force a 1v3.
3. Fire at will handles targeting; rw_ui_attack to focus grenadiers or the nearest melee rusher. Never chase fleeing raiders.
4. Drag wounded out of the line of fire at once (a bleeding pawn has ~2 hours). Undraft when the raid flees so pawns eat, sleep and tend.
5. After: haul loot, capture downed raiders, rebuild traps, repair walls.

## First raid with 3 colonists
Expect 1-2 poorly armed raiders (35-50 points). Before day 10: walled bedroom block with one door, 3-5 wood spike traps in the approach lane, a chunk or sandbag line, best gun on the best Shooting pawn. Fight from the doorway, others beside a wall corner; never fight in the open.

## Field notes (verified in my own colonies)
- **Let the steward's `combat` standing order draft and hold.** It drafts every violence-capable pawn to the rally point when hostiles have a path to the base and releases 600 ticks after the last one is gone. Do NOT draft by hand unless the rally is overrun or a pawn is mispositioned; a manual `ui.draft`/`ui.goto` pauses the combat order for that pawn ~1 h. So the correct raid move is: confirm the order is on, then only intervene on the specific pawn that is wrong.
- **Set a rally point inside the walls, one door, near the hospital:** `rw_steward_orders_rally(rect=[x,z,w,h])`. Without one the order holds pawns around the base centre (bad: they stand in the open). This is the first thing to do once the first walls exist. In ep.1 the rally was `[122,98,5,2]` inside the barracks, next to the north door `[124,97]` — the single real chokepoint.
- **Trap adjacency is a silent dead blueprint.** "Not placeable adjacent to another trap" also means a trap *blueprint* next to an already-built trap NEVER fills — it just sits there forever looking like a stalled build. Cancel it (`designator=cancel`) and stop re-placing it; leave the one trap, keep the lane otherwise clear.
- **Two chokepoint lanes, only one is really used.** I built the north door `[124,97]` + barricade rows at z95-96 and a second, decoy south door. Raiders path to the *nearest colonist*, so keep only ONE clearly-open route and let barricades line the approach 1-2 tiles outside the door (leave the door tile itself free to walk through).
- **Cheap levers before day 10:** raise steel by mining (300 target) for turret parts and components, and buy a **second ranged weapon** with silver (800+ buys a bolt-action/auto-pistol from a trader). One shooter (Shooting 4-6) plus one melee (Melee 13) held; a lone melee drifter "preparing" 100+ tiles away needs no draft — just let the combat order watch it.
- **Non-human hostiles are not raids.** A sealed tomb of `Fleshbeast` dark entities with `LordJob_FleshbeastAssault` sits ~110 tiles out; it only matters if it breaks out. Manhunter animals (`Manhunter hare` etc.): draft both violence-capable pawns, the fight is over in seconds (rifle + melee knife killed one hare, only a minor bite) — then undraft and tend.

Sources: Raid points; Raider; Pirates/Pawns; Tribes/Pawns; Defense tactics; Defense structures; Cover; Sandbags; Spike trap; Mini-turret; Drafting
