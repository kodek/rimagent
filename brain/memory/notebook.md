# Episode 3, seed rimagent-3 (TemperateForest, Summer)

## Colonists (3)
- Kena (Human926): Shooting 12!, Artistic 9!, Construction 8: BUILDER. Mood 92%. Idle/wandering.
- Lumi (Human929): Shooting 12!!, Melee 12!!, Social 7!: GROWER/COOK. Mood 41%. Sleeping.
- Kat (Human932): Medicine 11!!, Intellectual 13!!: DOCTOR/RESEARCHER. Mood 22% (CRITICAL, major threshold 20%).

## Day 15 21h - Kat mood crisis
Kat at 22%, major break threshold 20%. Top negatives:
- SleptInBarracks -7 (Room:7 has 3 beds = barracks; compound Room:1 also 3 beds = barracks)
- ObservedRottingCorpse -6 (raccoon [127,120], buzzard [108,125])
- Hungry -6 (food need 21%, holding MealSimple in inventory)
- NoFidelistUplifter -5 (ideo role unfilled, all 3 affected)
- Unsightly -5 (filth/corpses)
- SleptInHeat -4 (34-38C in barracks)
- AteWithoutTable -3
- Disturbed sleep -1
Positives: +40 (low expectations +24, comfortable +6, hope +5, recreation +5)

**Root cause of barracks moodlet:** No individual bedroom for Kat. Room:23 (4x3, 12 cells) is Kena's. Need to build a 5x5+ bedroom for Kat. **FLAG TO BUILDER.**

**Fixes in progress:**
- Cooler pressed to 11C (should reduce SleptInHeat in 6-12h)
- Kat assigned to compound bed (but compound is also a barracks, so -7 persists)
- Raccoon corpse needs hauling to dump zone

**If Kat drops below 20% (major break):**
- No one can tend her if she breaks
- Check: did she eat? Is catharsis fading?
- Emergency: build bedroom NOW, haul corpses, assign Fidelist Uplifter

## Base
- Room:7 Barracks 8x6 at [114,118], 34C, 3 beds + research + campfire + horseshoes
- Room:1 Compound 18x12 at [139,128], 38C, 3 steel beds + stove + generator + battery
- Room:23 Kena bedroom 4x3 at [108,120], 32C, 1 bed (dark)
- 3 spike traps, solar generator, 2 batteries
- Power: 1 net, 1000W gen, 40W consumption, 659wd stored

## Food
- food_days 5.3, 28 meals in stock, rice harvest ~1.3d
- 2 cooking bills on Campfire51575
- Policy: Lavish (matches MealSimple)

## Mood issues (Lumi 41%, Kat 22%)
- Lumi: ObservedRottingCorpse -6, NoFidelistUplifter -5, Unsightly -5, SleptInHeat -4, Sweaty -4, Insulted -5
- Kat: see above

## Threats
- threat_points 38. No hostiles on map.
- 8 corpses near base (2 rotting: raccoon [127,120], buzzard [108,125])

## Open / next
- **BUILD: Individual bedroom for Kat (5x5+ interior, 1 bed)** - top priority
- Haul raccoon + buzzard corpses to dump zone
- Assign Fidelist Uplifter role (check ideo tab / engine)
- Watch Kat mood: if drops below 20%, emergency
- Cooler should bring compound temp down in ~6-12h
- Rice harvest in ~1.3d - confirm harvest
- Research: all 164 projects done, no current project
- Wood at 657, Steel at 603, Silver at 823
