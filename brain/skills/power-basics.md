---
name: power-basics
description: Pull in whenever you build anything electrical (generator, battery, cooler, turret, lamp, workbench with power) or state.power shows unpowered consumers. How grids work, how to wire them with ui.wire, and the checks that catch a dead grid.
tags: [power, electricity, conduit, generator, battery, cooler, turret]
always: false
---
# Power in one page

A building only gets power if it is on a **power net**. A net is everything connected through **conduits** (1 steel each, `PowerConduit`, can run under walls and doors) or directly adjacent transmitters. Generators feed the net, batteries store it, consumers drain it. No conduit touching a consumer = no power, no matter how close the generator is.

Sources (Crashlanded starts with Electricity researched):
- `WoodFiredGenerator` 2x2, 1000 W, burns wood (needs refuelling; keep 50+ wood in reach and "auto refuel" on). 100 steel + 2 components.
- `SolarGenerator` 4x4, up to 1700 W by day, 0 at night (research SolarPanels). Needs batteries for nights.
- `WindTurbine` 2x7, variable, needs clear cells in front/behind (research).
- `GeothermalGenerator` on a steam geyser, 3600 W constant (research). The best mid-game source.
- `Battery` 1x2, stores 600 Wd, 70 steel + 2 components. MUST be roofed and indoors (rain shorts them, and they can explode: keep them in their own small room away from wood).

Consumers (typical): cooler 200 W (low power mode 20 W when at target), turret 400 W, standing lamp 30 W, electric stove 350 W, research bench 25 W, hydroponics 70 W, electric smelter 700 W, fabrication bench 250 W.

## Building a grid (the order that works)
1. Place the generator with 1 free cell around it (`rw_ui_build def=WoodFiredGenerator at=power:C`).
2. Place consumers where they belong (coolers IN the freezer wall, rot so the cold side faces in; turrets outside; lamps in dark rooms).
3. Wire: `rw_ui_wire(from="WoodFiredGenerator75793", to="Cooler77221")`. It path-finds and lays conduit blueprints; conduits under walls are fine. One wire per consumer is simplest; branches join automatically.
4. Batteries next to a conduit inside a roofed room.
5. After the builders finish: `rw_state_power` must show 1 net, `unpowered_consumers` empty, generation >= consumption. `rw_map_power(around=...)` shows the grid: digits are net ids, X is an unpowered consumer.

## Checks that catch dead grids
- `unpowered_consumers` lists every building that wants power and has none, with the nearest conduit cell: wire it there.
- Two different digits on `map.power` = two separate nets that need joining with one conduit.
- Generator "off" = out of fuel, or switched off (gizmo "Designate toggle power").
- Consumption > generation with empty batteries = brownout: everything flickers off. Add a generator or cut consumers.
- Coolers default to a 21C target. For a freezer press the cooler's `-10C` gizmo three times (target -9C or lower) and verify the room temp in `state.base`.
- Short circuit ("Zzzt") happens on conduits when batteries are charged; keep conduit runs short and batteries few, or accept the occasional fire (build a firefoam popper nearby).
