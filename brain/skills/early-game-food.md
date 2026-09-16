---
always: false
description: Pull in when food stock is under ~10 days, when placing the first growing
  zones or choosing a crop, before designating any animal for hunting, and when deciding
  how to cook (campfire vs stove, raw food, food poisoning). Also pull in when food_days
  is 0 or negative and you need to understand why the colony is starving.
name: early-game-food
tags: []
---

# Early-game food

## Core numbers
- An adult human burns **1.6 nutrition/day**, stores 1.0 max. Below 25% saturation = Hungry (-6 mood), below 12.5% = Ravenously hungry (-12), 0% = malnutrition (+2%/hour, death at 100%; ~72.5 h from full to death).
- 1 raw item (rice, potato, corn, meat, berries) = **0.05 nutrition**. A simple meal costs **0.5 nutrition (10 raw items)** and gives **0.9** (180% efficiency). Budget **~2 simple meals or ~32 raw units per colonist per day**.
- Raw rice/potatoes/corn/meat/eggs: **Ate raw food -7 mood** and 2% food-poisoning. Berries and milk: no mood penalty, still 2%.

## The food policy system (verified from FoodRestrictionDatabase.cs, RimWorld 1.6)
Food policies are a **live labeled database**, NOT a fixed enum. The labels that exist by default:
`Lavish, Fine, Simple, Paste, Raw, Nothing` (+ `Vegetarian, Carnivore, Cannibal, Insect meat` when Ideology is active).
**There is NO "Any" policy and NO "Survival" policy.** Passing either to `rw_ui_set_policies` errors ("unknown food policy value"). This was the root cause of ~30 failed `rw_ui_set_policies` calls in episode 3.

What each policy allows (by food category):
| Policy | survival packs | simple meals | fine meals | nutrient paste | raw food |
|---|---|---|---|---|---|
| Lavish | YES | YES | YES | YES | YES |
| Fine | YES | YES | no | no | YES |
| Simple | **NO** (explicitly disallowed) | no | no | no | YES |
| Paste | no | no | no | YES | no |
| Raw | no | no | no | no | YES |
| Nothing | no | no | no | no | no |

Key facts:
- **Survival packs (MealSurvivalPack, preferability 9) are edible ONLY under Lavish or Fine.** Simple explicitly `SetAllow(MealSurvivalPack, false)`.
- A **null** policy falls back to `DefaultFoodRestriction()` = the first DB entry = **Lavish** (allows everything).
- **To eat survival packs: set the policy to `Lavish` (or `Fine`).** Do NOT try "Any"/"Survival".
- **Use the `food_policy_set` tool** to set the policy on ALL colonists in one call (collapses N `rw_ui_set_policies` calls): `food_policy_set(policy="Lavish")`. `food_policy_set(action="list")` shows the live DB + each colonist's current policy.
- **Use `food_policy_check`** to see which colonists' policies block the food actually in stock, and what to set it to.

### The survival-pack starvation trap (#1 repeated cause)
Survival packs are a distinct category. If the only food is survival packs and a colonist's policy is Simple/Paste/Raw/Nothing, they will **not** eat them and will starve while 50 packs sit in the stockpile.
- **Fix: `food_policy_set(policy="Lavish")`** (or "Fine"). One call, all colonists.
- **On refugee intake:** a new colonist may carry a restrictive policy. Reset everyone to Lavish with one `food_policy_set` call.
- **On any food crisis:** first run `food_policy_check`. If it reports a mismatch, `food_policy_set` to the recommended policy before doing anything else.
- **The `food_policy_watcher` checks ALL colonists on each day tick** and fires when a policy excludes the food in stock. If it fires, run `food_policy_set` for the flagged colonists.

## Cooking bills, the #2 repeated failure
The second most common food crisis cause: rice harvests but nobody cooked it because the cooking bill was never set (or got suspended/duplicate-cleaned). This happened ~8 times across episodes.
- **`cook_bill` tool:** one call finds the best cooking station (FueledStove > Campfire) and sets a Forever CookMealSimple bill. Use it instead of 3-4 separate calls.
- **`cook_gap` watcher:** fires on day tick; if no CookMealSimple bill is running and food_days < 6, it auto-sets a Forever bill on the best station and wakes the planner.
- **Rule: after any food crisis, always verify a cooking bill is running** (check `food_outlook.cooking_bills`). If empty, run `cook_bill` immediately.
- **Operator tip: check for existing bills before placing new ones** — the campfire often has many duplicate CookMealSimple bills. Before adding a bill, call `rw_state_bills(thing=<id>)` and only add one if none exist. If duplicates exist, delete the extras (use `rw_ui_bill` with `id` param, not `index`, since indices shift after deletion).
- **Campfire work speed is 0.5x** (a 300-work meal takes 600). A fueled stove cooks 2x faster. Build a stove when you have the steel.
- **Simple meals rot in 4 days** at room temperature: cook small batches until a freezer exists.

## Crop comparison (normal soil; all need fertility >= 70%)
| Crop (def) | Grow days | Yield | Nutrition/harvest | Fertility sens. | Notes |
|---|---|---|---|---|---|
| Rice (Plant_Rice) | 3 | 6 | 0.30 | 100% | Fastest and most stable; 183% the labor of potatoes, 366% of corn. |
| Potato (Plant_Potato) | 5.8 | 11 | 0.55 | 40% | Best on gravel/stony soil; gains little from rich soil. |
| Corn (Plant_Corn) | 11.3 | 22 | 1.10 | 100% | Least labor; 150 HP; keeps without a freezer. One lost harvest hurts. |

Per tile per day all three are within ~5% (rice slightly ahead). Grow days assume full light and ideal temperature; night rest roughly doubles real time (potatoes ~10.7 days).

**Do this:** sow rice first. Once ~10 days of meals are banked, move most tiles to corn (less work per food). Use potatoes only when the fertile ground is gravel/stony. Within ~12 days of winter or a forecast cold snap, sow only rice; corn will not reach maturity and plants die below their minimum growth temperature.

## Field sizing and placement
- **10+ tiles per colonist** with year-round growing; **25 tiles per colonist** feeds one pawn indefinitely on Losing is Fun with a Plants-6 grower and Growing at priority 1. Add more for unskilled growers or short seasons.
- `rw_ui_zone`: only on unroofed soil with fertility >= 70% and light >= 51%, near the kitchen/stockpile. Leave 4-tile gaps between fields (blight radius) and strip flammable plants within 2 tiles (raiders light fields).
- Priorities: the steward scorer gives Growing to the best Plants pawn on its own; `rw_steward_explain(pawn=, work="Growing")` shows it. `rw_steward_posture(label="harvest", hours=12)` before a frost.

## "It will self-correct" is only true if ALL THREE hold (the #1 repeated failure)
A rice harvest "in 0.5 days" only saves you if:
1. **Somebody has Growing AND PlantCutting**, otherwise nobody cuts the rice and it just sits at 100% while the colony starves. The scorer raises both when food is low (`ConsiderLowFood`); check `rw_steward_status` pawns' `top`, and if a pawn is unmanaged (`managed: false`) with Growing 0, hand it back with `rw_steward_pawn(managed=true)` or set it yourself.
2. **A cook bill is running** (CookMealSimple on a campfire/stove), harvested raw rice is useless until cooked, and raw food gives -7 mood. Check `food_outlook.cooking_bills`; if empty, run `cook_bill` immediately.
3. **The food policy allows the food you have.** If you only have survival packs, the policy must be **Lavish or Fine** (NOT "Any"/"Survival" — those don't exist). If you have raw rice, the policy must allow raw (Lavish, Fine, Simple, or Raw). Run `food_policy_check` before calling a food crisis "self-correcting."
If any of the three is missing, the harvest ETA is meaningless. Verify all three before calling a food crisis "self-correcting."

## Campfire temperature in barracks (episode 3 lesson)
A campfire inside a small barracks (8x6 room) raises the room to **28-32C** in spring/summer, causing "Slept in the heat" (-4 mood) every night for all colonists. This is a recurring mood drain that compounds with other debuffs.
- **Fix options (in order of preference):**
  1. **Move the campfire outside** the barracks (next to the wall, still roofed). The interaction cell must be free.
  2. **Build a separate kitchen room** next to the barracks with the campfire/stove inside, and keep the barracks for sleeping only.
  3. **Add a cooler** in the barracks (requires Cooler research + steel). Overkill for early game.
- **If you can't move the campfire yet:** accept the -4 mood but note it in the notebook so you don't forget to fix it.

## Foraging
Wild berry bushes give berries (14 days to rot). The steward's `foraging` job harvests them toward 150+25n; this bridges days 1-5 until the first rice comes in. In a crisis raise it: `rw_steward_stock_set(kind="foraging", target=400)` then `rw_steward_stock_run(id=)` for an immediate pass (no mood penalty).

## Hunting safely
- Only pawns holding a **ranged weapon** hunt; never send melee. Hunters fire from max range; long-range, high-damage-per-shot weapons (bolt-action rifle, greatbow) are safest. Revenge chance is **3x higher at close range**. Check **Revenge chance on harm** (`rw_defs_get` or the Wildlife list). Prefer **0%** animals: deer, gazelle, alpaca, dromedary. Do NOT hunt predators, boomrats/boomalopes (explode and start fires), or herd species with revenge chance: one manhunter can pull every same-species animal within 25 tiles.
- Hunting stealth = 5% per Shooting level + 5% per Animals level (cap 90%); low-skill hunters take only safe or already-injured prey. No incendiary weapons.
- **Hunted herbivores cost the hunter -15 mood** ("killed innocent animal") for days; in a small fragile colony keep the steward's meat target low (`rw_steward_stock_set(kind="hunting", target=150)`) rather than hunting aggressively. Hunting is designated by the steward toward the meat target; you set the target and `hunt_predators`, not the animals.

## Butchering and cooking
- **ALWAYS build a butcher spot (ButcherSpot) as soon as you plan to hunt** (operator tip). Without it, hunted animals are wasted — the meat never gets processed.
- **ALWAYS set a bill on the butcher spot** (operator tip): `rw_ui_add_bill(thing=<ButcherSpotId>, recipe="ButcherCorpseFlesh", mode="Forever")`. Without the bill, colonists won't butcher corpses brought to it.
- Drop a butcher spot immediately (free, 0 work) but it yields only 70% meat/leather; build a butcher table when materials allow. Raw meat rots in 2 days, vegetables ~30 days longer.
- `rw_ui_build` def **Campfire**: 20 wood, burns 10 wood/day, holds 20, must sit under a roof (rain burns extra fuel). `rw_ui_add_bill` "simple meal, do until you have 10-15". Campfire work speed factor is 0.5 (a 300-work meal takes 600); a fueled stove cooks 2x faster and unlocks fine meals.
- Give Cooking to the highest-skill cook. Food-poison chance by Cooking level: 0 = 5%, 3 = 2%, 4 = 1.5%, 6 = 0.5%, 8+ = 0.15% or less, scaled by kitchen cleanliness and difficulty (Losing is Fun x1.2). Skill 3+ in a clean room already beats raw food. Nutrient paste (dispenser + power) is 300% efficient and never poisons.

Sources: Rice plant; Potato plant; Corn plant; Nutrition; Food; Saturation; Growing zone; Simple meal; Meals; Campfire; Food Poison Chance; Hunt; Hunting Stealth; Food production; Raw food; Berries; Butcher spot; FoodRestrictionDatabase.cs