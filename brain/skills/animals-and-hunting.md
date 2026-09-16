---
always: false
description: Pull in before changing the steward's hunting target or hunt_predators,
  before designating tame on any wild animal, when a predator or manhunter pack is on
  the map, or when deciding which animals to keep, pen, train or butcher.
name: animals-and-hunting
tags:
- animals
- hunting
- taming
- predators
- manhunter
- pens
- food
---

# Animals and hunting

## Temperate-forest wildlife
Meat = 140 x body size (butcher spot 70%; kills by damage 66%). Revenge chance triples at close range.

| Animal | Revenge hurt | Revenge tame fail | Size / ~meat | Wildness | Notes |
|---|---|---|---|---|---|
| Squirrel, Hare | 0% | 0% | 0.2 / ~30 | 75% | Low value |
| Turkey | 0% | 0% | 0.6 / 84 | 45% | Easy meat |
| Wild boar | 0% | 0% | 0.85 / 119 | 50% | Herd |
| Deer | 0% | 0% | 1.2 / 168 | 75% | Best early hunt target |
| Alpaca | 0% | 0% | 1.0 / 140 | 25% | 45 wool per shear, pack animal |
| Muffalo | 10% | 0% | 2.4 / 336 | 60% | 120 wool per shear, pack animal |
| Elk | 0% | 0% | 2.1 / 294 | 75% | Herd, milkable |
| Timber wolf | 100% | 30% | 0.85 / 119 | 85% | Predator |
| Cougar | 50% | 30% | 1.0 / 140 | 80% | Predator, 6.7 s stun |
| Grizzly bear | 50% | 30% | 2.15 / 301 | 80% | Predator, 7 s stun, power 200 |

## Hunting rules
1. The steward's `hunting` job designates animals toward the meat target (300+75n) and the leather target (100), safe species first, no predators (`hunt_predators=false`), never within 30 cells of hostiles. You set targets (`rw_steward_stock_set(kind="hunting", target=)`), not animals; `rw_ui_designate hunt` only for one specific animal (a wounded one at the door, a revenge-free target the job skipped). Only ranged pawns hunt; hunters shoot from max range, finish the downed animal and haul it. Melee provokes any species.
2. Prefer 0% revenge species (deer, elk, boar, turkey); restrict the job with `allow=["Deer","Elk"]` if it keeps picking herd animals. Never set `hunt_predators=true` with one shooter.
3. Suspend hunting while rw_state_threats shows hostiles (`rw_steward_stock_set(kind="hunting", suspended=true)` or posture `defend`), in rain or snow (accuracy penalty), or into a muffalo herd. Wounded animals bleed out; do not chase them.
4. **Distance is not a concern.** (Operator tip, episode 3: "anything on the map is fair game, who cares how far away animals are.") Hunt any animal on the map regardless of distance. The 30-cell rule was removed.
5. **Butcher table is mandatory.** (Operator tip: "always build a butchering spot otherwise hunting is wasted!") Build a TableButcher; the `corpses` standing order keeps a standing butcher bill on it (and places a ButcherSpot once if none exists when the first carcass lands). Intervene when the order is off or `rw_state_bills` on the table is empty: `rw_ui_add_bill(thing=<butcher table>, recipe="ButcherCorpseFlesh", mode="TargetCount", count=20)` (the RecipeDef is `ButcherCorpseFlesh`; there is no `ButcherCorpse`), or the `set_bill` brain tool, which uses the right recipe and skips duplicates. Check for existing bills before placing new ones (operator tip: "check for existing bills before placing them as campfire has many dupes").
6. There are plenty of animals on the map. If food_days is low, raise the meat target and force a pass (`rw_steward_stock_run`); a `stock_stalled` on hunting means no safe target in radius: raise `max_radius` to 0 (whole map).

## Predators
Wolves, cougars and bears hunt anything smaller than themselves, pets and colonists included, when no meat or corpses are nearby. Their first strike stuns, and they keep attacking downed prey.
- On a "predator hunting" alert: rw_ui_draft 2-3 armed pawns and kill it together (a predator stalking wildlife is not hostile, so the combat order stays out; undraft them after), or keep everyone indoors and let it eat wildlife. The `rescue` order carries a downed victim; check its summary rather than ordering the rescue yourself.
- Predators ignore penned animals unless they wander in.

## Manhunter packs and mad animals
Pack points are 40% above a raid's; only fence-passing species are picked. They cannot open doors but bash one they saw you use, and linger 24-54 hours.
- Response: everyone indoors, doors closed, pets restricted inside. Fight only through a held-open door or 1-wide gap with melee blockers. Scaria may rot corpses.
- A mad animal charges the nearest human: draft 2-3 pawns and shoot it.

## Taming and training
- Tame chance multiplier is 2 x (1 - wildness): dogs/chickens 2x, alpaca 1.5x, muffalo 0.8x, deer 0.5x, bear/cougar 0.4x, wolf 0.3x. Bear, wolf and cougar attack 30% of the time on failure. Handlers need non-meal food matching the diet.
- Tame early: alpaca (wool, caravans, easy), muffalo (wool, pack animal), chickens (population doubles every ~5.7 days, eggs keep 15 days), labrador or husky (0% wildness, advanced trainability).
- Animals above 10.1% wildness lose training and tameness unless penned; the scorer gives Handling to the best Animals skill once tamed animals exist (check `rw_steward_status`). Cap a breeding herd with `rw_steward_stock_add(kind="livestock", species="Chicken", max=6)` (`allow`/`disallow` on livestock jobs name trainables, not species; `rw_steward_stock_set(id=<int>, max=N)` changes the cap).
- Training: Guard (3 steps) follows a master; Attack (5) can be released on enemies; Rescue (2) and Haul (7) need advanced intelligence (dogs, wolves, cougars, bears). Attack-capable animals add 8% of combat power to raid points.
- Hunger per day: muffalo/elk 0.535, husky 0.5, alpaca 0.275, chicken 0.14; 1 hay or meat = 0.05 nutrition.

## Pens (1.6)
Farm animals (trainability "none": muffalo, alpaca, boar, chicken, turkey, deer, elk) ignore allowed areas and roam off the map unless roped into a pen: a pen marker (30 stuff) enclosed by fences, walls or doors with at least one gate (rw_ui_build Fence / FenceGate / PenMarker). A 20x20 grass pen barely feeds 4 pigs; build big and stock hay for winter. Raiders never target pen animals; cap herds with auto-slaughter.

Sources: Animals; Animal husbandry; Pen; Meat Amount; Wildness; Training; Deer; Elk; Wild boar; Grizzly bear; Timber wolf; Cougar; Alpaca; Muffalo; Hare; Squirrel; Turkey; Chicken; Labrador retriever; Husky; Events