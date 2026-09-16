# Colony notebook, episode 1, seed rimagent-1 (COMPACTED day 6)

Temperate forest, spring, 12 Aprimay. home ~[126,106]. 3 colonists, all healthy.
wealth 17.0k (items 9.8k / bldg 3.8k), threat 35, mood 62, food_days 6.1, temp_out 11C (seasonal 19).

COLONISTS
- Bat (Human570) Construction 8!!, Plants 8!!, Animals 6!, Int 5, Sho 4, Slowpoke. Bolt-action rifle. Hunts (Animals 6).
- Kalie (Human573) Social 9!!, Medicine 7!!, Crafting 5!!. INCAPABLE OF VIOLENCE, unarmed. Best doctor.
- Josephine (Human576) Artistic 14!!, Melee 13!!!, Social 7. Plasteel knife. Incapable: Cook/Con/Grow/Mine/PlantCut/Craft/Smith/Tailor/Haul/Research.

BASE
- Barracks x119-128 z97-104 (room 34), N door [124,97], temp was 28C -> campfire Campfire39362 deconstruct-designated (heat penalty; spring is warm, drop it).
- Kitchen x119-128 z106-111 (room 42, 18C, dark -> TorchLamp blueprint [121,108]). Doors: S to outside [124,112], and to barracks.
- "main" stockpile = kitchen 47 cells, Overflowing (48 stacks outside, 34 unroofed/deteriorating).
- NEW STOREHOUSE (blueprint only, day 6): granite wall outline [134,102,8,6] + wood door [134,104] rot E; interior zone "store" [135,103,6,4], priority Important, Foods+Corpses DISALLOWED (food stays in kitchen "main"). ~1545 work; only Bat builds.
- South vestibule: wall row z112 built except the door [124,112]; z113 has built walls 119-121,126-128 + frames 122,123,125. I CANCELLED Blueprint_Wall [124,113] so the south door path stays open. Do not put a wall back there.
- North chokepoint (the real one): door [124,97], barricades z95-96 x119-128, TrapSpike [121,95]+[127,95], stray Blueprint_TrapSpike [121,95] (NEVER fills: trap can't be adjacent to a trap - leave it).
- Rally = [122,98,5,2] inside the barracks. Combat order handles drafting.
- Tomb Room:21 [235,92] 110 tiles E: 4 fleshbeasts (Fingerspike/Bulbfreak) sealed in, no door. Leave; watch for break-out.

STEWARD
- stock: forestry 800 (759), foraging 225 (231), hunting MEAT target LOWERED 525->120 (15 meat, 5 designated), hunting_leather 100 (9, starved), mining steel 300 (178), production meals 40 (17/40 bill ok).
- posture "build-out" 36h: Construction +0.5, Growing +0.3, Cooking +0.3, Hauling -0.3, Hunting -0.5 (so Bat builds, not hunts).
- orders all on (combat/rescue/fire/unforbid/corpses/beds/policies/blueprints).

FOOD: 29 meals + 50 berries + 12 survival packs + 15 meat = 6.1 d. rice1 x129-137 z112-118 (53 cells) first harvest in progress (0.7 growth). FueledStove42090 has CookMealSimple TargetCount 40.

RESEARCH: Batteries 26/400 current; queue SolarPanels > Pemmican > Smithing. SimpleResearchBench in barracks.

DEFENSE FORECAST: day 8-11 raid, expect 2 raiders. Only Bat shoots (Shooting 4, bolt-action); Josephine melee 13. Kalie cannot fight. WANT: a second ranged weapon (buy with 800 silver if a trader comes) + keep the north barricade line repaired.

NEXT CHECKS (in order): 1) does the storehouse frame count fall (Bat building?) - if frozen, raise Construction posture/check granite blocks; 2) south door [124,112] path still walkable; 3) food_days after rice harvest; 4) corpses: 5 on map (2 human-like) - let corpses order bury/burn; 5) mood: watch slept-in-heat vs slept-in-cold after campfire removal.

[improvement pass day 7] No colony changes. New tools: defense_readiness (threats+our armed/drafted+defenses near home, one call), storage_report (stockpile zones + outside_storage overflow verdict). New watcher daily_audit (once per in-game day: wakes on food_days<4, mood_avg<38, build queue unchanged a whole day; nags if >=5 stacks rotting). Tightened defense-basics with field notes (trap-adjacency dead blueprint; rally point inside walls is the first post-wall job; combat order handles drafting so only intervene per-pawn). Journaled 2 lessons.
