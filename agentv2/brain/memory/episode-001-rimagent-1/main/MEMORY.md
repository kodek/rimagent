# Game: Crashlanded, day 0 (6 Aprimay), Rough. Pawns: Mila (Human884, Cook 11/Plants 10/Med 8), Ace (Human887, Shooting 8), Potts (Human890, Mining 11/Intel 5).

## Layout (all blueprints placed day0 13h, frames pending)
- Room: walls x120-129/z132-140, door [124,132] rot N. Beds: [122,139]E, [126,139]E, [121,136]S. Campfire [124,136]. FueledStove [125,134] rot N (3x1 covers x124-126). Research bench [125,137] rot N (footprint x124-126,z137-138).
- STILL TO PLACE: HandTailoringBench (stuff WoodLog, 3x1; interaction cell is south of body) -> try [121,134] rot W or [122,135] rot E; also Table + 2 stools for mood.
- Stockpile "main" rect [121,125,8,7]. Rice field "rice1" rect [134,134,10,5] (50 cells, Plant_Rice, ~3 day grow). Home area set [118,124,28,18] (606 cells).
- Rally rect set: [120,132,10,9].

## Steward
- Research queue: Batteries (started) -> Pemmican -> Smithing -> Devilstrand -> SolarPanels -> DrugProduction -> Machining -> Gunsmithing -> BlowbackOperation -> GunTurrets -> MicroelectronicsBasics. Potts (Intel 5) researches once bench built.
- Stock targets: forestry 1500 (LOW BACK TO 500 once room built); hunting 120 (was 525); mining 300 ok; foraging 225.
- Trees cut-designated in room/stockpile/field.

## Orders given
- Ace: equip bolt-action rifle (Gun_BoltActionRifle3631 @ [116,129]). Mila: STILL NEEDS revolver (Gun_Revolver3632 @ [111,128]) - order at next wake.

## Next steps (in order)
1. Verify frames==0 + room_digest shows bedroom w/ indoor temp; if stuck, raise Construction posture.
2. Add CookMealSimple (TargetCount 10) bills on stove AND campfire (built ids via map.find).
3. Tailoring bench + table + stools.
4. Winter plan: Devilstrand research -> Mila (Plants 10) sows devilstrand; or cloth from fluff dusters; FueledStove already placed for winter heat.
5. First raid ~day 5-10 (35 threat pts). Keep weapons equipped; rally set.

## Updated day0 17h
- Both guns equipped: Ace bolt rifle, Mila revolver (orders given; Ace already had rifle when hunting).
- Placed: Table2x2c [122,133], stools [121,133]+[124,133], HandTailoringBench [122,138] rot N (body x121-123 z138, chair (122,137)).
- Posture "build" active 24h: Construction +0.5, Hauling -0.5 (+ Mining/PlantCutting/Smithing up, Research -0.2) — fixes all-Construction-4 freeze.
- Corpses standing order auto-placed ButcherSpot (blueprint) at (127,129) + ButcherCorpseFlesh bill.
- 17h state: 44 blueprints, 0 frames; Mila sowing rice, Ace hunting, Potts hauling. Wood 683.
- NEXT: when stove+campfire built (map.find def) add CookMealSimple TargetCount 10 on each; verify room_digest shows bedroom; drop forestry target to 500.
