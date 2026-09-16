---
name: storyteller-and-threats
description: Pull in when planning the colony's first year, deciding whether to keep or sell loot, reading an incident letter (raid, manhunters, fallout, flare, drone, infestation), or judging how big the next threat will be.
tags: [storyteller, cassandra, wealth, threats, incidents, difficulty]
always: false
---
# Storyteller and threats

## Cassandra Classic pacing
- Intro threats are fixed: one mad animal, then one lone raider at day 5 hour 15.
- The cycle starts day 11: 4.6-day "On" phases alternating with 6-day "Off" phases (On 11.0-15.6, 21.6-26.2, 32.2-36.8, 42.8-47.4, then +10.6 each). Each On phase sends 1-2 major threats, at least 1.9 days apart; ~8.5 per year. Off phases are safe windows for caravans, big builds and surgery.
- Major threat weights: raid 9.0, infestation 2.8 (needs 400 points, 20-day refire), manhunter pack 2.0 (15-day refire), psychic ship 1.5, mad animals 1.0.
- Raid types gate on points: mechanoids and centre drop pods need 300, sieges 500, sappers/breachers 700.

## What sets threat size
Raid points = (Wealth points + Pawn points) x Threat scale x Starting factor x Adaption factor. Check wealth via rw_state_summary.
- Storyteller wealth = items + creatures + 0.5 x buildings.
- Wealth points: 0 until 14,000 wealth, then ~1 point per 161 wealth up to 2,400 at 400,000.
- Pawn points: 15 per colonist under 10,000 wealth, 140 at 400,000 (15 + (wealth - 10,000)/3,120). Combined, 1 raid point costs ~139 wealth at 3 colonists, ~106 at 10. Attack-capable animals add 8% of their combat power.
- Starting factor: 0.7 through day 10, 1.0 by day 40. Adaption starts at 0.8, cannot rise for 30 days, and drops when colonists are downed (6 AdaptDays at pop 2-3) or die (30).
- Threat scale: Strive to survive 1.00 (the setting formerly called "Rough"), Blood and dust 1.55, Losing is fun 2.20, Adventure story 0.60.
- 1 point buys ~1 combat power: tribal 30-60, well-armed pirate 90, scyther 150, centipede 400. Test case: 3 colonists at 104k wealth gaining ~20k of beer went from 3 to 4 scythers on Strive.

## Wealth management rules
1. Do not overproduce. Each colonist eats ~20 raw food/day; a 5x5 normal-soil plot feeds one colonist year-round. No hundred-meal stockpiles.
2. Loot is wealth: a fresh corpse ~250, a heavy SMG 355, a dozen raider guns thousands. Let corpses rot (2 days, then worth 0), smelt junk weapons, gift surplus to factions, or dump it from a caravan.
3. Invest rather than hoard silver: buy components, better guns, armor, rockets, skilltrainers, things consumed or that protect you.
4. Below Strive to survive wealth barely matters; focus on gear. Above it, every ~140 wealth is a raid point at 3 colonists.

## First-year incident playbook
| Incident | Numbers | Response |
|---|---|---|
| Raid | see defense-basics | Draft behind cover at the chokepoint |
| Mad animal | one animal, charges nearest human | Draft 2-3 pawns, shoot it together |
| Manhunter pack | 40% more points than a raid; lingers 24-54 h; cannot open doors | Everyone indoors, doors closed, shoot through a held-open door; scaria may rot corpses |
| Disease (flu/plague/malaria) | plague kills in ~1.5 days untreated | Bed rest immediately, medicine, rw_ui_set_policies medical NormalOrWorse or better |
| Cold snap / heat wave | 1.5-3.5 days, 30-day refire | Heaters/campfires or coolers, keep pawns indoors, harvest crops early |
| Toxic fallout | 2.5-10.5 days, not before day 60; 40% buildup/day outdoors, permanent damage at 40% | Restrict everyone to a roofed area via rw_ui_set_policies area; bring animals under roof; expect crops to die |
| Solar flare | 0.15-0.5 days; all electric devices off | Turrets, heaters, coolers dead: pull pawns back to a defensible door, use campfires |
| Eclipse | 0.75-1.25 days, no solar, crops pause | Batteries; otherwise ignore |
| Psychic drone | -12 to -40 mood on one gender, 0.75-1.75 days; Low level under 800 points | Reduce other stressors; keep the affected gender off risky work |
| Infestation | needs overhead mountain within 30 tiles of a building, warm (>-8 C), dark | Avoid bedrooms under mountain early; if it spawns, kite insects (they guard 10 tiles) and burn hives |

Pitfall: a downed colonist lowers adaption (easier next raid); a dead one adds corpse wealth and mood debuffs. Rescue first, then destroy loot you will not use.

Sources: Cassandra Classic; AI Storytellers; Raid points; Wealth; Wealth management; Events; Disease; Infestation
