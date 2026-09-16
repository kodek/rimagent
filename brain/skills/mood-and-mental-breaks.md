---
always: false
description: Pull in when a colonist's mood is below ~40%, a mental break alert fires,
  or when planning day 1-5 furniture (tables, beds, recreation) to prevent breaks.
name: mood-and-mental-breaks
tags:
- mood
- mental-break
- recreation
- rooms
- early-game
- catharsis
---

# Mood and mental breaks

## Thresholds (rw_state_pawn)
- Base mood by difficulty: Peaceful/Community builder 42, Adventure story 37, Strive to survive 32, Blood and dust 27, Losing is Fun 22; thoughts add to it.
- `break_thresholds` in `state.pawn` is `[minor, major, extreme]` as percentages (e.g. `[35, 20, 5]`). No engine call needed.
- Mean time to break below a line: minor 10 days, major 3 days, extreme 0.7 days. Sleeping/unconscious pawns cannot break.

## The three mood zones (mood_triage now covers all three)
| Zone | Mood range | Severity | Action |
|---|---|---|---|
| **at_risk** | below minor (35%) but above major (20%) | `at_risk` | Fix the biggest negative NOW; 10 days to break if unaddressed |
| **critical** | below major (20%) | `critical` | Emergency: fix root cause, draft others, wake in 1-2h |
| **extreme** | below extreme (5%) | `extreme` | Berserk imminent; draft everyone, keep clear |

`mood_triage` flags every colonist below the **minor** threshold and returns `severity` per pawn. Use it whenever any colonist is below 35% — not just when `mood_watch` fires.

## The catharsis-fade crash (the #1 pattern that catches you off guard)
After any mental break, the colonist gets **catharsis +40** (or +30 for minor). This buff fades over ~2 days. While it's active, the colonist's displayed mood looks fine (e.g. 50%) even though the underlying debuff (alcohol withdrawal -35, malnutrition -26) is still there. When the catharsis fades, mood crashes to (real_mood - catharsis_value) and the break threshold is crossed.

**Rule: when a colonist has a catharsis buff, compute the post-fade mood = displayed_mood - catharsis_value. If that number is below the major threshold, treat it as an emergency NOW, not after the crash.**

`mood_triage` returns `catharsis_buffer` per flagged pawn so you can see this without reading each pawn individually.

**`food_crisis_triage`** also checks all colonists for catharsis crashes in one call (along with food status) — use it when both food and mood are in crisis simultaneously (the common refugee-influx pattern).

## Simultaneous extreme-break crisis (episode 2 lesson)
When **two or more colonists are simultaneously below their major threshold** (or one is at extreme and the other's catharsis is fading below major), the colony is in a death spiral:
1. **No one can tend the other.** If both are in breaks, no one is tending the downed one, no one is building, no one is cooking.
2. **Check the root cause first.** In episode 2: both colonists were starving (food policy excluded survival packs) → malnutrition -26 → mood collapse → breaks. Fix the food policy BEFORE trying to fix mood.
3. **If the root cause is food:** the `policies` order already switches everyone to a raw-allowing policy (`steward-raw`: raw food and meals, no corpses/insect meat/kibble) when meals drop under 2 per colonist and restores the old policy at 4 per colonist. Intervene when the food in stock is one that policy still blocks: survival packs only -> `food_policy_set(policy="Lavish")` (a hand-set policy is left alone by the order for 2 days). The malnutrition debuff clears within ~12h of eating.
4. **If the root cause is drug withdrawal:** you cannot fix it without the drug. Accept the break or trade for the drug.
5. **If both will break and there is no recovery path** (no food, no medicine, no recovery path): note it in the notebook and consider ending the episode honestly. Do not waste steps on a lost cause.
6. **Wake in 1-2 hours** when both are at extreme risk. Check: did they eat? Did the catharsis fade? Is the mood still below threshold?

## How to triage a low-mood colonist (use `mood_triage` tool)
One call: `mood_triage()` returns for every colonist below their **minor** threshold:
- `mood`, `severity` (`at_risk` or `critical`), `minor_threshold`, `major_threshold`, `extreme_threshold`
- `catharsis_buffer`: the catharsis thought if present (check its `mood` value to compute post-fade mood)
- `top_negatives`: top 5 negative thoughts sorted by value

Fix the biggest negative first. The usual hierarchy:
1. **Alcohol/drug withdrawal (-35)**, finish Brewing research, build FermentingBarrel, make beer. No other fix.
2. **Malnutrition (-26)**, food crisis; fix food before mood. **Check the food policy first** (see early-game-food skill).
3. **Killed innocent animal (-15)**, keep the steward's meat target low (150) so it hunts sparingly; the scorer rotates hunters.
4. **Confined interior (-10)**, expand bedroom to ≥5×5 interior.
5. **Rotting/observed corpse (-6)**, the `corpses` order buries, hauls or burns them within the hour (never mid-raid); if the debuff persists there is no grave, no `corpses` stockpile and no fire to burn with: build a grave. **Desiccated corpses cannot be hauled** — use `destroy_corpses` tool (sandbox mode) or move the dump zone far from base.
6. **Darkness (-5), Unsightly (-5), Tattered apparel (-5)**, light, clean, tailor.

## Crisis debuffs that recur (the ones that actually broke colonists in play)
| Debuff | Mood | Source / fix |
|---|---|---|
| **Alcohol/drug withdrawal** | **-35** | A colonist with an addiction who has NO drug in the colony. The single largest early mood killer. If a refugee arrives with an addiction, you MUST bank that drug (or accept the break). Check each new colonist's `needs` for a drug need; set drug policy to allow it. |
| **Malnutrition** | **-26** | Food crisis. The `policies` order switches to `steward-raw` when meals run short; **check the food policy** only when the stock is something it still blocks (survival packs under "Simple"), then `food_policy_set(policy="Lavish")` before anything else. |
| Ate corpse meat | -12 | During a food crisis pawns eat corpses; each is -12 and a rot-stink source. Avoid by keeping ANY food above 0. |
| Ate raw food | -7 | Expected while the `policies` order has everyone on `steward-raw` (meals < 2 per colonist); it restores the cooked policy at 4 per colonist. Fix the meal supply (bill, cook, ingredients), not the policy. |
| Killed innocent animal | -15 | Hunting herbivores, the hunter eats -15 for days. Hunt sparingly, rotate hunters, only when food is critical. |
| Observed/rotting corpse | -4 / -6 | Corpses near the base cause -6 to ALL colonists. The `corpses` order buries/hauls/burns; give it a grave or a `corpses` stockpile. **Desiccated corpses cannot be hauled** — use `destroy_corpses` tool (sandbox) or relocate dump zone. |
| No shepherd role (mod) | -5 | Some mods add a "Shepherd" ideo role; unfilled it is -5 to everyone. |

## Common early debuffs (exact values)
| Thought | Mood | Fix |
|---|---|---|
| Ate without table | -3 | Table + stool/chair adjacent |
| Slept outside | -4 | Enclosed, roofed room |
| Slept on ground | -4 | Real bed |
| Slept in the cold / heat | -4 each | Heater/cooler, insulate |
| Disturbed sleep | -1, stacks to -3 | Private bedroom per pawn |
| Soaking wet | -3 | Roof over paths |
| Ratty apparel (20-50% HP) / Tattered (<20%) | -3 / -5 | Tailor replacements |
| Confined interior (room < ~25 tiles) | -10 | Bedroom must be >= 5x5 interior; a 2-cell room is a -10 trap |
| Unsightly/ugly environment | -3.5 to -4 | Clean filth, smooth floors/walls |
| Badly malnourished | -26 | Food crisis; a starving colonist breaks fast, fix food before mood |

## Confined interior, the small-bedroom trap (verified day 10)
A bedroom smaller than ~25 interior tiles gives "Confined interior" (-10). A 2-cell room is the worst case and a real break trigger on its own. Always build bedrooms at least 5×5 interior (>= 25 tiles). Check room size with `rw_state_rooms`; if a colonist's bedroom is small, expand it rather than leaving the -10.

## Common buffs
- Beauty need >65% gives Pretty environment (+2.5 to +4.5).
- Comfort >60% gives Comfortable; a normal bed is 0.75.
- Recreation 70-85% = satisfied, below 30% = unfulfilled, 0 = starved.
- Catharsis after a break: +30 (minor), +40 (major/extreme), fades over ~2 days.

## Watchers and tools
- **`mood_watch`** watcher: fires on `day`, `colonist_downed`, and `mental_break` events. Checks every colonist's mood against their major threshold AND the catharsis-fade crash. Wakes the planner with a specific alert.
- **`mood_triage`** tool: one-call triage for all below-minor-threshold colonists.
- **`food_crisis_triage`** tool: combined food + mood triage (use when both are in crisis simultaneously, e.g. refugee influx).

## When a colonist is in a mental break
- **NOT berserk (Wander_Psychotic, Wandering, etc.):** let it play out. The break ends in 1-3 days. Do NOT draft them. Do NOT try to tend them. Just keep the colony safe and let the catharsis kick in when it ends.
- **Berserk (Berserk, WildMan):** draft everyone, keep clear, use blunt weapons only. A berserk colonist can only be stopped by blunt melee (no guns, no sharp weapons). If they are in the barracks, the damage will be severe.
- **After the break ends:** the colonist gets catharsis (+30/+40). The mood will look fine for ~2 days. Compute the post-fade mood NOW and plan for the crash.

## Heatstroke and mood (episode 4 pattern)
In dry biomes, rooms without coolers reach 37-38C in summer. This causes:
- "Slept in the heat" (-4) every night
- Heatstroke hediffs (severity 0.3-0.5) that compound with other debuffs
- No power = no coolers = no fix until power is built
**Prevention:** build a wood-fired generator + battery + cooler BEFORE the first hot night. Cost ≈ 200 steel + 2 components. If you cannot build power, accept the -4 mood and note it.