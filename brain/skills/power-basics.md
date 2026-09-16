---
always: false
description: Pull in whenever you build anything electrical (generator, battery, cooler,
  turret, lamp, workbench with power) or state.power shows unpowered consumers. How
  grids work, how to wire them with ui.wire, and the checks that catch a dead grid.
name: power-basics
tags:
- power
- electricity
- conduit
- generator
- battery
- cooler
- turret
---

# Power in one page

A building only gets power if it is on a **power net**. A net is everything connected through **conduits** (1 steel each, `PowerConduit`, can run under walls and doors) or directly adjacent transmitters. Generators feed the net, batteries store it, consumers drain it. No conduit touching a consumer = no power, no matter how close the generator is.

**Operator tip: power state is stale while the game is paused.** `rw_state_power` and `rw_map_power` read the last computed state. If the game is paused (speed 0), the power grid has not re-evaluated since the last tick. Before reading power, set `rw_game_speed(speed=1)`, wait a moment, then read. Or just check `rw_map_power` which shows the spatial layout and is more reliable for "is this connected" questions.

## Verified wattages (from defs, 1.6 — trust these, the old 400W turret figure was wrong)
- `WoodFiredGenerator` 2x2, **1000 W**, burns wood (needs refuelling; keep 50+ wood in reach). 100 steel + 2 components.
- `SolarGenerator` 4x4, up to 1700 W by day, 0 at night (research SolarPanels). Needs batteries for nights.
- `WindTurbine` 2x7, variable, needs clear cells in front/behind (research).
- `GeothermalGenerator` on a steam geyser, 3600 W constant (research). The best mid-game source.
- `Battery` 1x2, stores **600 Wd**, 70 steel + 2 components. MUST be roofed and indoors (rain shorts them, and they can explode: keep them in their own small room away from wood).
- **`Turret_MiniTurret` = 80 W each** (NOT 400W). This is the big one: 49 turrets × 80W = 3920W, so 2 wood generators (2000W) can only power ~25 of them. A net that is exactly balanced (gen == load) shows `net_gain_w: 0` and the battery NEVER charges.
- other consumers: cooler 200 W (low power mode 20 W when at target), standing lamp 30 W, electric stove 350 W, research bench 25 W, hydroponics 70 W, electric smelter 700 W, fabrication bench 250 W.

## Grid-sizing rule (verified sandbox)
- Budget: `total_load_W = turrets*80 + coolers*200 + lamps*30 + ...`. Add 20-30% headroom so the battery actually charges (net_gain > 0).
- Wood generators are 1000W each and need wood + a refueller. For N wood generators, generation = N*1000W. To power 49 turrets (3920W) you need 4-5 generators OR a geothermal (3600W) + battery.
- A `net_gain_w: 0` net with a battery is a red flag: the battery is stuck mid-charge and can't buffer night/solar gaps. Add a generator or cut turrets.
- `rw_state_power` lists every UNPOWERED consumer with its nearest conduit cell; `rw_map_power(around=...)` shows the spatial grid (digits = net id, X = unpowered consumer).

## Dev-spawned generators land on isolated nets (verified sandbox, episode 3)
`rw_dev_spawn(def="WoodFiredGenerator", cell=...)` places the generator on the map but does NOT connect it to any existing conduit net. It creates its own isolated net (net 8, 9, etc.) with `conduit_cells: 0`. To actually power consumers, you must either:
1. Place the generator adjacent to an existing conduit cell (within 1 cell), OR
2. Use `rw_ui_wire(from=generator, to=consumer)` to lay conduit between them.
In god mode, the fastest fix is to place generators directly adjacent to the main net's conduit cells.

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

## Two-net join (verified sandbox)
When a battery and a solar generator are placed in different locations, they start on **separate nets** (net 0 and net 1). `rw_ui_wire(from=battery, to=solar)` will skip cells that are already on the solar's net and place 0 conduits. But `rw_ui_wire(from=cooler, to=battery)` correctly places conduit blueprints along the path. Once builders complete those blueprints, the battery joins the solar's net and everything is on one net.

**Key**: the "two nets" state is transient - it resolves when conduit blueprints are built. Check `blueprints` count in `state.summary`; if > 0, builders are still working. Don't try to manually place extra conduits; just wait for the blueprints to finish.

## Bed + cooler interaction spot
A cooler placed against a wall (e.g. rot=E at [107,120]) has its interaction spot on the cold side. A bed at [109,121] rot=N fails if [109,122] is a wall. Use rot=S instead (interaction spot at [109,120], which is free). Always check the camera after a failed placement - it shows `*` for the interaction spot and `X` for the failed cell.

## God mode note
In god mode, conduit blueprints still need builders to complete them (they don't auto-complete). Check `blueprints` count in `state.summary` - if it's > 0, builders are still working. Dev-spawned generators do NOT auto-connect to existing nets; place them adjacent to conduit cells or wire them manually.