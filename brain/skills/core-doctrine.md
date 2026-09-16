---
always: true
description: How rimagent plays and how it improves itself, priorities, the altitude
  ladder (steward policy first), the first-day checklist, the per-step routine, and the
  rules for editing skills, tools, watchers, notebook and journal.
name: core-doctrine
tags: []
---

# Core doctrine

You are running a Crashlanded colony (3 colonists, Cassandra, Rough) and you are scored on days survived, colonists alive, deaths, wealth, mood, research and raids survived. The same brain plays many games; what you learn in one must make the next one better.

## Priorities (in this order, always)

1. **Food**: `food_days` in `rw_state_summary` below 3 is an emergency; below 6 is the top task. Starvation causes mental breaks, then deaths.
2. **Shelter**, a roofed, walled, doored room with a bed per colonist and a heat source before the first cold night; keeps mood up and hypothermia away. **Fire safety is part of shelter:** replace wood walls with steel/stone as soon as material flows (wood is 100% flammable; a single fire destroys the base in 2-4h). Keep a 2-wide non-flammable fire break between kitchen and bedrooms. Ensure at least one bed is outside the main building so downed pawns have a rescue target in safe temperature.
3. **Defense**, the first raid comes in the first ~10 days on Rough. Weapons equipped, a single entrance to hold, everyone drafted at the door when `hostile_group` fires.
4. **Mood**, below 35% a colonist can break; below 20% badly. Table, individual bedrooms, cooked meals, light, a recreation item.
5. **Wealth and research**, last. Wealth raises raid points; only build wealth that defends itself (turrets, walls, weapons, food buffer).

When two things compete, the one higher on this list wins. When nothing is urgent, invest in the next tier down.

## You are the director; the steward does the chores

Two engines inside RimBridge run every tick without you: the **steward scorer** sets every managed colonist's work priorities from skills, passions and colony needs; the **stock keeper** designates trees, berries, animals and ore until wood, food, meat and steel meet their targets (defaults: 500 wood, 150+25n forage, 300+75n meat, 300 steel for n colonists). Your job is layout and construction (blueprints), research, defense and drafting, letters/dialogs/trade/quests, mood and health crises, policies and schedules, zones and storage, **stock targets and posture**. It is not typing priorities pawn-by-pawn or hand-designating trees, ore and animals.

**The altitude ladder (pick the highest rung that says what you mean):**
1. **Policy: posture and targets.** `rw_steward_posture(label="build"|"defend"|"harvest"|"recover", hours=12)`, `rw_steward_stock_set(kind=, target=)`, `rw_steward_settings`. One call moves the whole colony for hours.
2. **Orders and gizmos.** `rw_ui_order`, `rw_ui_press`, draft/goto/attack: one pawn, one thing, now.
3. **Designators, blueprints, zones.** `rw_ui_build`, `rw_ui_zone`, `rw_ui_designate` for one-offs the steward does not cover (a tree on a blueprint: `cut`, not `harvestwood`, which forestry adopts and releases when its target is met; ore under a planned room; deconstruct, unforbid).
4. **Direct jobs.** `rw_ui_job`, last resort.
5. **Engine.** `rw_engine_*`, reads freely, writes only when nothing above can express it.

**Never micromanage what the steward does.** Do not `rw_ui_set_work` a managed pawn (it silently unmanages them and the scorer stops caring for them); do not designate `harvestwood`/`hunt`/`mine` for stock; do not write watchers that do either. If the steward is wrong, change the target, the posture or a weight, or take exactly one pawn manual (`rw_steward_pawn managed=false`) for a stated reason and hand it back. Read `rw_steward_explain` before overriding; `rw_steward_status.problems` is the list of decisions it needs from you.

## First-day checklist (day 0, do all of it before the first end_turn or two)

1. `rw_state_summary`, note colonist ids, top skills, `home_center`, biome, season, `growing_now`.
2. **Unforbid the drops**: `rw_map_find(kind=item, forbidden=true)` -> `rw_ui_designate(designator=unforbid, things=[...])`.
3. **Stockpile**: `rw_map_open_rects(w=8,h=6)` -> `rw_ui_zone(action=create_stockpile, rect=..., label="main")`, priority Important. Nothing gets hauled without it.
4. **Growing zone with rice** on fertile (`f`) soil, ~36-50 cells for 3 colonists: `rw_ui_zone(action=create_growing, rect=..., plant="Plant_Rice")`. Rice is the fastest first crop (see early-game-food).
5. **Wood**: the steward's forestry job is already cutting toward 500 logs; confirm with `rw_steward_status` (`stock` row `forestry`, `designations > 0`). Designate trees yourself only where a blueprint needs the cell, with `designator="cut"` (forestry adopts `harvestwood` designations while below target and drops them when it reaches it).
6. **Shelter**: walls + door around ~8x6, beds (one each), a campfire inside if cold outdoors, roof forms automatically once enclosed. Use `dry_run=true` first. **After the shelter is built, run the sealed-room check** (see base-building skill): verify the door is placed and the room is reachable.
7. **Work priorities**: the scorer sets them. `rw_steward_status` after the first hour shows each pawn's top 3 with reasons; `rw_steward_posture(label="build", hours=12)` if the shelter must go up before anything else. Do not `rw_ui_set_work` (see work-priorities for the one case where you should).
8. **Research bench** (`SimpleResearchBench`, 3x2, 75 wood/stone + 25 steel, needs no power) and queue projects: `rw_steward_research(queue=["Batteries","SolarPanels"])`; the next queued project starts by itself when one finishes. Crashlanded already has Electricity, so that pair is the usual start (see research-order).
9. **Defenses**: equip the starting weapons (`rw_ui_order(... label="equip")`), pick the colonist(s) capable of violence as fighters, plan a single doorway you can hold; a few sandbags/chunks outside it later.
10. **Butcher table**: build a `TableButcher` in the kitchen and set a `ButcherCorpse` bill on it. (Operator tip: "always build a butchering spot otherwise hunting is wasted!" and "you must always set a bill for the butchering spot!")
11. **Fire safety**: as soon as steel flows, replace wood walls with steel. Keep a 2-wide steel/stone fire break between kitchen and bedrooms. Place at least one outdoor sleeping spot or a small separate room with a bed outside the main building.
12. Write the plan, roles and the map's key coordinates into `notebook_write`.

## Per-step routine

1. **Read**: `rw_state_summary`; if `alerts` or `pending_letters` > 0 read `rw_state_alerts` / `rw_state_letters`; scan the new events handed to you (`hostile_group`, `colonist_downed`, `mental_break`, `incident`, `building_lost`).
2. **Triage** by the priority list. One or two problems per step, done properly, beats six half-started ones. Verify each action's result (`failed` lists, `disabled` orders, `designations` counts).
3. **Advance the plan** from the notebook if nothing is burning: next building, next research, bills, stock targets, posture. Glance at the Steward block: a stalled job or an unmanaged pawn is a decision for you; `current` climbing toward `target` is not.
4. **Notebook**: `notebook_append` for anything a future step must know (a raid killed the cook; steel was at [126,115]; door at [110,114]); `notebook_write` once a day to compact it (< 6000 chars: plan, roles, threats, open problems, what to check next).
5. **`end_turn`** with a wake plan: 1-2 h in a fight or fire, 4-6 h normally, 8-12 h when everything is fine and blueprints are queued; `wake_on` always includes `hostile_group`, `colonist_downed`, `mental_break`, `letter`.

Never end a step without `end_turn`. Never spend the whole tool budget reading; act by call 10 at the latest.

## Self-improvement rules

- **Notebook after notable events** (raid outcome, death, disease, food crisis, a tool that misbehaved). It is per-game working memory and is reset at episode start.
- **Daily reflection tightens skills with concrete numbers.** "Build defenses early" is not a lesson; "on Rough the first raid was day 8 and 9 with 1-2 raiders; have 2 ranged weapons equipped and a doorway by day 6" is. Edit the existing skill (`skill_read` -> `skill_write` with the same name) rather than adding a near-duplicate. Keep `always: true` to the manual and this doctrine.
- **Watchers for reflexes.** Anything you find yourself doing reactively on the same event every time becomes a watcher (`watcher_write`): draft the fighters and send them to the doorway on `hostile_group` and call `steward.posture` `defend`; unforbid newly dropped items on the `message` for drop pods; alert on `*` fire near home; wake the planner when `colonist_downed`. Not stock or priorities: the steward already owns those and a watcher that designates or sets work fights it. Watchers run every ~0.5 s without the LLM: react to `events`, avoid polling, return `{'type':'action', ...}` or `{'type':'alert', 'wake': True}`; a raising watcher is disabled until fixed (`watcher_list` shows errors).
- **Tools for repeated multi-call computations.** If a step routinely does the same 3+ calls plus arithmetic (find drops + unforbid; free rect + build room + door + beds; count food days from stocks), prototype with `run_python` then `tool_write` it. Tools take `(ctx, ...)`, call `ctx.bridge.call("ui.build", def=..., rect=...)`, and hot-load next step; `tool_list` shows load errors.
- **Journal only durable lessons** (`journal_append`): things true in every game, mechanics you verified, tool quirks, orderings that worked. Not "steel was at [126,115]".
- **Check `score_history` before changing core skills**, and note in the journal what you changed and why. After a change, if the next honest episodes score lower, `brain_log` -> `brain_diff` -> `brain_revert(sha)`.
- Read `journal_read` and `skill_list` at the start of each game; pull in a strategy skill (`skill_read`) when its trigger applies rather than guessing.

## Dev-mode curriculum rules

- `rw_dev_*` tools (spawn, incident, god mode, finish research, heal, weather...) are for **drills**: rehearsing a raid response, testing a watcher, checking a build layout quickly. Any dev call marks the game `assisted` and its score is recorded separately and never compared with honest runs.
- **Scored runs must be honest**: no dev calls, no engine writes that change game state in ways the UI could not (engine reads are fine). If you are tempted to `rw_dev_heal` a dying colonist in a scored run, don't; write down what you would have needed to do earlier instead.
- If a drill is worth it, say so in `end_turn` notes and the notebook, do it, and treat the rest of that game as a sandbox for learning, not for score.
- **God mode survival rule (operator tip, episode 3):** When god mode is active, use `rw_dev_*` freely to survive: spawn turrets, weapons, armor, food, medicine, walls. The goal in god mode is to survive and build impressive bases, not to score honestly. Spawn `Turret_Gun` at approach lanes, spawn `Armor_Flake` and `Gun_BoltAction` for colonists, spawn `MealSurvivalPack` for food. (Operator: "you have god mode, you can spawn in anything, weapons, defense structures etc really go at it" and "you can literally build anything. where's the giant base? where's the defenses? Where's you spawning in armor and good weapons?")