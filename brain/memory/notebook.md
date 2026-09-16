# Colony notebook, episode 1, seed rimagent-1

## Day 2, 13h — Spring, TemperateForest
3 colonists: Velasquez (Artistic 10, Shooting 8, Animals 8), Allison (Cooking 6, Medicine 4, Mining 3, incapable of violence), Ophelia (Shooting 9, Construction 9, Animals 4)

## Base
- **Barracks** (Room:28) 7x5 at [113,123]–[119,127], door at [116,122] (south, to outside)
  - Beds: Ophelia [113,126], Allison [115,126], Velasquez [117,126]
  - Research bench [114,124], Campfire [116,124], Butcher table [118,124]
  - StandingLamp blueprint at [119,127]
  - Temp 28C, impressiveness -28 (needs table/furniture; too tight for table)
- **ButcherSpot** at [104,120]
- **WoodFiredGenerator** at [122,126] (2x2, east of barracks), auto-refuel ON
- **Stockpile "main"** at [101,121], 47 cells
- **Rice zone "rice1"** at [129,144], 36 cells
- **Rally point**: [115,123,3,2] (inside barracks, near door)

## Defenses (queued)
- 2× Spike traps at [115,121] and [117,121] (flanking door approach)
- Sandbags at [116,121] (center of door approach)
- All blueprints pending wood (26 wood, need ~90 for traps)

## Power
- Grid live: 1000W gen, 9 conduit cells, research bench connected
- No battery yet (needs Batteries research, 2% progress)
- StandingLamp will need 30W when built

## Weapons
- Ophelia: Bolt-action rifle (equipping)
- Velasquez: Revolver (equipping)
- Allison: incapable of violence (no weapon possible)

## Research
- Current: Batteries (2%)
- Queue: Batteries → SolarPanels → Firefoam → Hydroponics

## Stocks
- Wood: 26 (forestry target raised to 600, 11 trees designated)
- Steel: 762/300 ✓, Components: 28, Silver: 800
- Food: 10.3 days, 54 meals total, rice growing

## Steward
- All orders active, rally set
- Forestry 26/600 ↑, Foraging 5/225, Hunting 11/525, Mining 771/300 ✓
- Production (meals) 13/22

## Next steps
1. Wait for wood → traps + sandbags build
2. Build Battery when Batteries research done
3. Plan freezer (Cooler x2 in south wall) after SolarPanels
4. Build steel walls to replace wood (fire safety)
5. Consider turrets after Firefoam research
6. Watch for first raid (~day 5-10, threat points 35)

## Open issues
- Barracks too tight for dining table (impressiveness -28)
- No battery yet
- Room:26 (2 cells at [138,238]) is a stray, ignore
- Room:20 Tomb at [236,92] is ancient, not ours

Day 3, 11h: Trader Blue Mink visited and left. Manhunter rat at [211,67] (111 cells away) — combat order will draft shooters when it gets close. Wood critically low (27 logs) for defense blueprints (4 traps + 1 sandbag need ~180 wood). Forestry has 14 trees designated, pawns busy hunting/butchering. Batteries research at 6%. Food 11 days, mood 59-65.

Day 3 18h: Manhunter rat chasing Allison (110 cells from base, 75% health, minor blood loss). Ophelia drafted to intercept at [225,22]. Velasquez at rally. NEW: 4 dark entities (Fingerspike, Toughspike, 2x Bulbfreak) at [239-243,92-98], 124-129 cells away, LordJob_FleshbeastAssault, fogged, near tomb. These are a bigger threat than the rat.

Day 3, 11h: Trader Blue Mink visited and left. Manhunter rat at [211,67] (111 cells from base, 75% health, minor blood loss). Ophelia drafted to intercept at [225,22]. Velasquez at rally. NEW: 4 dark entities (Fingerspike, Toughspike, 2x Bulbfreak) at [239-243,92-98], 124-129 cells away, LordJob_FleshbeastAssault, fogged, near tomb. These are a bigger threat than the rat.

Day 3 ~2h: Manhunter rat killed. 2 colonists downed far from base (Ophelia 40%, Allison 30%, both bleeding). Velasquez (only able, 71%, bleeding) rescuing Allison first (most critical). All 3 set to Best medical. 4 dark entities (Fingerspike/Toughspike/2 Bulbfreak) 124+ cells away, fogged, LordJob_FleshbeastAssault — watch them. Wood still low (27) for defense blueprints.

Day 3 2h: Ophelia died (blood loss). Allison downed 30% health at [196,36], Velasquez (71%, bleeding) rescuing her. 4 dark entities (Fingerspike/Toughspike/2 Bulbfreak) at [239-243,92-98], 124+ cells from base, LordJob_FleshbeastAssault — far enough to have time. Let Velasquez finish rescue, then deal with fleshbeasts. Mood avg 27%, Velasquez 43%.

Day 3, 4h: Ophelia died (blood loss). Allison died (downed, 31%). Velasquez is the LAST colonist: 73% health, bleeding, 5% food, mood 27 (below 35% break threshold). Self-tend ON, eating simple meal. 4 dark entities (Fingerspike, Toughspike, 2x Bulbfreak) at [239-243, 92-98], 124-129 cells from base, LordJob_FleshbeastAssault. No turrets. Rally point set at [115,123,3,2]. Blueprints: 2 spike traps + 1 sandbag (stuck, no wood). Combat order will draft Velasquez when entities get close. Mood: Velasquez 27%, below minor break threshold - biggest negatives: hunger (-12, being fixed), pain (-10), barracks (-7), witnessed death (-5).

Day 4: NEW colonist Chris (StrangerInBlack, faction Player, Medicine 11, Shooting 14, Revolver) joined and is tending downed Velasquez. Colony no longer alone — Chris can fight (Shooting 14) and medic. Velasquez downed 77% health, bleeding, mood 37. 4 fleshbeasts (Fingerspike/Toughspike/2 Bulbfreak) at [239-243,92-98], 124-129 cells, LordJob_FleshbeastAssault, fogged. Automation added this pass: combat_triage tool, defend_on_hostile watcher (auto defend posture on hostile_group), best_med_on_downed watcher (auto Best medical on downed).
