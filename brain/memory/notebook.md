# Episode 3, seed rimagent-3 (TemperateForest, Summer)

## Day 20, 7h — Improvement pass (no colony actions)

## Brain changes this step
- **hunt_distance_guard** watcher: fires on day tick if pending Hunt designations exist but armed colonists < 2. Alerts planner to cancel unsafe hunts.
- **hunt_safety** tool: one-call check of all pending Hunt designations vs. animal distance from home. Flags >30 cells as unsafe. Also lists nearest safe animals.
- **starvation_gap** watcher: fires on day tick if food_days < 2 AND no meat-bearing animals within 30 cells. Alerts planner of the gap.
- **idle_colonist** watcher: fires on day tick if any colonist is idle (wandering/relaxing) — prompts work priority audit.
- **work-priorities skill**: added verified defName table + "common wrong names" section (Misc, Cutting, Fueling, Researching, Building all wrong).

## Colonists (3)
- Kena (Human926): Shooting 12!, Artistic 9!, Construction 8: BUILDER. Mood 74%.
- Lumi (Human929): Shooting 12!!, Melee 12!!, Social 7!: GROWER/COOK. Mood 87% (catharsis +40).
- Kat (Human932): Medicine 11!!, Intellectual 13!!: DOCTOR/RESEARCHER. Mood 52%.

## Food CRISIS (food_days 0.8)
- 4 meals + 8 raw rice in storage. Rice: 38 plants, 20.3% avg growth, est 2.4d to harvest.
- GAP: food runs out in 0.8d, harvest in 2.4d. No animals within 30 cells.
- Cook bill set on FueledStove92905. 5 hunt designations queued (animals 52-57 cells away — UNSAFE per 30-cell rule).
- starvation_gap watcher will fire on next day tick.

## Mood
- Kena 74%, Lumi 87% (catharsis +40, post-fade ~47%), Kat 52%.
- Kat negatives: AwfulBarracks -7, rotting corpse -6, unsightly -5, slept in heat -4, no table -3.

## Research
- ALL 164 projects complete.

## Base
- Room:7 Barracks 8x6 [114,118], 28C, 3 beds + research + campfire + horseshoes + lamp
- Room:1 Compound 18x12 [139,128], 31C, 3 steel beds + stove + generator + battery
- Room:23 Kena bedroom 4x3 [108,120], 25C
- Room:33 Bedroom 5x5 [117,127], 24C (assigned to Lumi)
- Power: 1000W gen, 100W consumption, 600wd stored
- 0 blueprints pending. 5 hunt designations pending.

## Threats
- threat_points 46. No hostiles on map. 14 desiccated corpses in dump zone.

## Open / next
- Food crisis: 0.8d food, 2.4d to harvest, no safe animals. starvation_gap watcher will fire.
- Kat mood 52%: needs private bedroom + table + cooler.
- 0 medicine left.
- Hunt designations: 5 pending, all unsafe (>30 cells). Cancel or wait.

## Notes
- Sandbox mode: assisted=true
- wood 501, steel 529, silver 823
- Temp dropped to 19C outdoor (night cooling)
