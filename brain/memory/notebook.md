# Episode 1, seed rimagent-1 — plan

Colonists (Crashlanded, temperate forest, 2C spring):
- Gideon Human1001: Melee 8!!, Social 6!, Medicine 5!, Plants 4!, Shooting 3. Traits Wimp, Jogger. -> revolver (equipped day0)
- Ateron Human1004: Melee 11!!, Social 9!, Intellect 7!, Crafting 4. Brawler, Recluse, NightOwl. -> plasteel knife + flak helmet
- Kuhn Human1007: Medicine 9!!, Intellect 9!!, Crafting 8!!, Construction 4!, Shooting 4!. Nimble, Industrious, Ascetic. -> bolt-action rifle (equipped day0)

BASE (home center [131,127]):
- Core room A: walls rect [126,122,11,9] wood, door at [131,122] (S side). Interior x127..135, z123..129. Beds at (134,123),(134,125),(134,127) rot E; campfire (133,126).
- Main stockpile: rect x127..133, z123..129 (col x131 removed for corridor) ~28 cells, priority Important.
- Room B (east): walls [137,122,11,1] N, [137,130,11,1] S, [147,123,1,7] E, door at [136,126] connecting to A. Simple research bench at [139,125].
- Rice field "rice1": [128,132,7,6] = 42 cells, Plant_Rice.
- All trees cut in [126,122,22,10] (80 designated).

Research: current Batteries; queue SolarPanels, Pemmican, Devilstrand, Smithing.

Steward: forestry target 800 (clears build area), foraging 225, hunting 525/100, mining 300. Rally set [128,123,8,4].

LOOT (forbid/unforbid): steel ~900 in base area (19 stacks x75), 500+300 silver, 30 components, 30 medicine, 50 packaged meals at ~[130,122]-[134,131]. Remote forbidden steel: [173,136] x46, [57,105] area x~240, [38,208] area x~222, [239,29] area x~212. 4 survival meals at [21,81].

NEXT CHECKS: walls built? beds built? stockpile hauling steel? Kuhn research. Then beds/tables, batteries+solar power, kill box at south door.

Day 0 21h: base nearly enclosed (walls x126/z122/z130 built; south of roomB x136-147 still frames). Research bench BUILT at [139,125]. Campfire [133,126] with CookMealSimple bill target 22 but 0 cooked — nobody has Cooking above 4 (Gideon 0, Ateron 4, Kuhn 0); steward gives everyone Hauling 1 because items deteriorate outside. Set posture "warmup" 24h: Construction +0.4, Cooking +0.5, forestry x1.5.
WARM CLOTHES (High alert): parkas need CLOTH/wool, not leather (Make_Apparel_Parka = 80 cloth). Sowed cotton1 zone [138,137,6,6] (36 cells, cut 13 plants in it). Built HandTailoringBench blueprint [143,127] rot S (75 wood). NEXT: when built add bills Make_Apparel_Parka x3 + Tuque; when Batteries done build solar+battery+Heater (50 steel/1 comp) in room A.
Stockpile "main" extended +35 cells ([142,123,5,7]) = 62 cells total (was full). Monolith letter closed.

Improvement pass (day 1): added tools build_report/food_report/room (brain/tools/colony_ops.py) and watcher raid_prep (raid/fire/downed -> clock to 1x + wake). Tightened skills base-building (ui.build REQUIRES explicit stuff; build_many layouts) and work-priorities (steward Hauling-1 artifact + posture fix; audit stove bill before priorities). Bridge was unreachable at the start of this pass (connection refused) - no colony changes made, as instructed. Next step: first check rw_state_summary, wall frames closed?, meals cooked?, parka/tuque bills when tailoring bench is built.
