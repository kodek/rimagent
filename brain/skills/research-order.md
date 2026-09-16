---
name: research-order
description: Pull in when choosing or changing the research project (rw_ui_set_research), building a research bench, or asking what a Crashlanded colony already has unlocked.
tags: [research, tech, early-game, electricity, priorities]
always: false
---
# Research order for a 3-colonist Crashlanded start

## What Crashlanded already has
New Arrivals (Crashlanded, Rich Explorer, Naked Brutality) start at Industrial tech level with Passive cooler, Stonecutting, Complex clothing, Complex furniture, Electricity, Air conditioning and Nutrient paste already researched, so beds, tables, coolers, wind turbines, stonecutting and tailoring are available on day 1. Crashlanded lands with 800 silver, 50 packaged survival meals, 30 components, 30 medicine, 450 steel, 300 wood, a bolt-action rifle, a revolver and a plasteel knife. Never queue those seven projects. New Arrivals pay base cost (tribes pay 1.5x medieval, 2x industrial).

## Bench and speed
- Simple research bench: 75 stuff + 25 steel, 2800 work, no research needed, x0.75 rate, cannot go past Microelectronics. Build it indoors on day 2-3 after beds and a stockpile (rw_ui_build).
- Hi-tech research bench: Microelectronics, 150 stuff + 100 steel + 10 components, 5000 work, 250 W, x1.0 rate, Construction 6.
- Research speed = 8% + 11.5% per Intellectual level, scaled by Manipulation and Sight, then x0.7 in bad temperature, x0.9 outdoors, cleanliness x0.75 (very dirty) to x1.09 (sterile). Use a lit, clean, roofed room and give the top Intellectual pawn Research 1-2. Extra researchers and benches stack; progress is kept when switching projects.

## Recommended order (cost in research points, prerequisites)
| # | Project | Cost | Needs | Why it matters for 3 pawns |
|---|---|---|---|---|
| 1 | Battery | 400 | Electricity | Stores wind/solar output so coolers, lamps and turrets run at night |
| 2 | Solar panel | 600 | Electricity | Steady daytime power; 100 steel + 3 components each, Construction 6 |
| 3 | Pemmican | 500 | none | Campfire recipe, 70 days to rot; food security before a freezer |
| 4 | Devilstrand | 800 | none | Best early fabric (1.40 sharp armor factor, 20 cold / 24 heat insulation); 22.5 grow days, Plants 10 to sow, so start early |
| 5 | Smithing | 700 | none | Smithy, melee weapons, needed for Machining |
| 6 | Machining | 1000 | Electricity, Smithing | Machining table (150 steel + 5 components) for guns |
| 7 | Gunsmithing | 500 | Machining | Revolvers, shotguns, bolt-action rifles |
| 8 | Blowback operation | 500 | Gunsmithing | Autopistols/machine pistols; gate for turrets |
| 9 | Gun turrets | 500 | Blowback operation | Mini-turret: 30 stuff + 70 steel + components, 12 damage, range 28.9; an extra gun for 3 pawns |
| 10 | Drug production | 500 | none | Drug lab; prerequisite for Penoxycyline production (500) and Medicine production |
| 11 | Hydroponics | 700 | Electricity | Basins (100 steel + 1 component), fertility twice rich soil; for cold or barren maps, skip on fertile temperate ones |
| 12 | Microelectronics | 3000 | Electricity | Hi-tech bench, comms console (trading); gates Hospital bed (1200, plus Sterile materials 600), Medicine production (1500, plus Drug production), Multi-analyzer |
| 13 | Beer brewing | 400 | none | Brewery and vats; cheap recreation, low priority until hops grow |

Optional: Watermill generator (700) on a river; Geothermal power (3200) near a steam geyser.

## Operating rules
- Queue with rw_ui_set_research using the ResearchProjectDef defName; labels differ from defNames (verified: Batteries, SolarPanels, Pemmican, Devilstrand, Smithing, DrugProduction, Brewing, WatermillGenerator, SterileMaterials, Autodoors), so confirm the rest with rw_state_research (lists `available` defNames) or rw_defs_get first.
- Budget the 30 starting components before choosing power research: wind turbine 100 steel + 2 components, battery 70 steel + 2, cooler 90 steel + 3, solar 100 steel + 3, machining table 5, hi-tech bench 10.
- Triggers: meat spoiling in heat -> Battery first (coolers are already unlocked); first raid larger than 3 -> Machining then Gun turrets; disease with no medicine -> Drug production then Penoxycyline production; short growing season -> Hydroponics before Devilstrand.
- Delay Microelectronics (3000) until the cheaper projects whose buildings you will actually construct are done; on a x0.75 simple bench with one mid-Intellectual researcher it takes many days.

Sources: Research; Scenario system; Research bench; Simple research bench; Hi-tech research bench; Research Speed; Wind turbine; Battery; Solar generator; Cooler; Pemmican; Devilstrand (plant); Devilstrand; Machining table; Mini-turret; Hydroponics basin; Beer
