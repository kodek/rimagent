---
name: temperature-and-seasons
description: Pull in when a cold snap, heat wave or season change is announced, when pawns show hypothermia/heatstroke or "slept in the cold/heat", when placing heaters/coolers/passive coolers/vents, when choosing clothing, or when deciding if crops can still be sown before winter.
tags: [temperature, seasons, cold, heat, clothing, buildings]
always: false
---
# Temperature and seasons

## Human thresholds (baseline, no clothing)
- Comfortable range **16-26 C**; outside it pawns get Cold/Hot mood penalties. Sleeping below 16 C gives **Slept in the cold -4** (above 26 C, Slept in the heat); **clothing never prevents sleep moodlets**, only heating the bedroom does.
- **Hypothermia** starts **10 C below** minimum comfort, **heatstroke 10 C above** maximum. Stages: 4% shivering, 20% minor, 35% serious, 62% extreme, **100% death**. Frostbite possible from 37% hypothermia in freezing spots.
- Rate: 10-21 C below comfort takes ~32 h to 100%; 50 C below ~9 h. Recovery in a warm room ~3.6 h. Burns begin 150 C above comfort.
- Check `rw_state_pawn` hediffs; past ~20% severity, `rw_ui_goto` the pawn into a heated/cooled room.

## Calendar
Year = 4 quadrums of 15 days: Aprimay (1-15), Jugust (16-30), Septober (31-45), Decembary (46-60) = spring/summer/fall/winter in the north (reversed south; equator temperate). Northern growing period usually runs early Aprimay to mid/late Septober; the growing-zone inspect pane shows the local one. Plants grow only 06:00-19:12 at 51%+ light. Below a crop's minimum growth temperature growth stops and plants "die due to cold" (`rw_defs_get` Plant_Rice/Plant_Corn for the value). Sowing that cannot reach ~66% maturity before the cold is wasted work.

## Incidents
- **Cold snap**: outdoor temperature drops over 4.8 h, lasts **1.5-3.5 days**, 30-day cooldown. Kills crops (harvest anything near maturity at once), wild plants become inedible so predators hunt pawns; may snow.
- **Heat wave**: same duration and cooldown, plus random map fires; freezers may thaw, heatstroke outdoors.
- On either warning: keep pawns in controlled rooms, watch room temperatures in `rw_state_summary`, refuel campfires/passive coolers.

## Buildings
| Def | Cost | Effect | Power/fuel | Notes |
|---|---|---|---|---|
| Campfire | 20 wood, 200 work | +21 heat/s, caps at **28 C** | 10 wood/day, holds 20 | Roof it (rain eats fuel); no target setting, can overheat small rooms. |
| Passive cooler | 50 wood, 200 work | -11 heat/s, floor **17 C** | 10 wood/day, 50-wood refill every 5 days | No power; cannot refrigerate; mass them in heat waves. |
| Heater | 50 steel + 1 component, 1000 work, Construction 5, Electricity | +21 heat/s to target | 175 W on, 17 W idle | Placement anywhere in room. One holds a 9x9 exterior room. |
| Cooler | 90 steel + 3 components, 1600 work, Construction 5, Air conditioning | -21 heat/s cold side, heats other side | 200 W on, 20 W idle | Wall-mounted: blue side in, red side outdoors or a 1x1 unroofed cell; blocked by impassable objects. One cools a 10x10 room; 2-3 to freeze it. |
| Vent | 30 steel, 400 work, Complex furniture | Equalizes two rooms, impassable | none | Heat one central room and vent outward; chains lose efficiency. |

Freezer: coolers below 0 C (spoilage stops at freezing; from 10 to 0 C it slows by temp/10). Over ~50 tiles use 2 coolers at 0 C and -2 C so one idles. Never open a freezer wall in summer to add a cooler: the room snaps to outdoor temperature.

## Insulation rules
- A room holds its own temperature only when **>= 75% roofed**; open doors and roof gaps equalize fast; a breach in an exterior wall resets it to outdoors instantly.
- Heat leaks through walls in cardinal directions only; a second wall layer helps, a third does nothing; material is irrelevant. Square rooms lose heat slower than corridors. Airlock = two doors in sequence with a 1-tile gap.

## Clothing (cloth, normal quality; wool and guinea pig fur insulate more)
| Item (cold factor x cloth 18) | Cold | Heat |
|---|---|---|
| Parka (2.0) | +36 C | 0 |
| Jacket (0.8) | +14.4 C | +5.4 C |
| Duster (0.6 / 0.85) | +10.8 C | +15.3 C |
| Tuque (0.5, fabric only, blocks helmets) | +9 C | 0 |

Craft parkas (80 stuff, Complex clothing) before winter in cold biomes; jackets suffice in mild ones. In heat, parkas insulate nothing: move pawns to dusters, cowboy hats or tribalwear and cool rooms with passive coolers. Work benches drop to 70% speed in bad temperatures.

Sources: Temperature; Comfortable Temperature; Human; Ailments; Hediffs/Core/Global/Temperature/Hypothermia; Hediffs/Core/Global/Temperature/Heatstroke; Events; Time; Growing zone; Campfire; Passive cooler; Heater; Cooler; Vent; Parka; Jacket; Duster; Tuque; Cloth; Clothing; Insulation - Cold
