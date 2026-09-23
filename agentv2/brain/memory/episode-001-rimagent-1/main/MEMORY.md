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

## Day 2, 6h state (all built: blueprints 0, frames 0)
- Room enclosed & warm: Barracks 56 cells, indoor 28°; all 3 slept in beds overnight (bed alert gone).
- Research STALLED: Batteries 0%. Potts Research 3 / Hauling 1. Posture "cookresearch" active 24h (Cooking +0.5, Research +0.5). CHECK: if Batteries still 0% next wake, force Potts (rw_ui_set_work Research 1) or check bench reachability (bench x124-126,z137-138, chair (125,136) free).
- Cooking auto: production stock job id 6 keeps CookMealSimple TargetCount 22 on Campfire39894 (interval 1h). Stove FueledStove40280 has no bill of its own — fine. MealSimple 2 stored.
- DEFENSE decision: NO spike traps yet — the approach lane south of door (124,131) is inside stockpile "main" rect; haulers would trigger their own traps. When raid letter arrives: combat order auto-drafts to rally [120,132,10,9]; Ace rifle + Mila revolver hold the door; Potts unarmed (knife). "Need defenses" High alert tolerated meanwhile.
- WARM CLOTHES (High alert, forecast for winter): cloth 0, leather 0. Need fluff dusters -> check map animals; hunt + butcher gives cloth, then tailor warm clothes (HandTailoringBench40246 @ [122,138], no bills yet).
- Food 8.8 days (meals_all 42 + meat 8 + berries). Rice (50 cells) growing; harvest ~day 3-4.
- Stocks: wood 896 (forestry target 1500), steel 984, silver 800. Foraging stuck "no valid wild plants".
- Moods good: Mila 63, Ace 64, Potts 57.

## Day 3, 16h
- Batteries 22% and Potts "researching" — cookresearch posture WORKS.
- Manhunter hare (Hare41338, was [80,130]) hunting pawns: Ace ordered to approach+shoot ([115,144] cast pos); combat order also active. Check next wake if still alive.
- Letters: monolith VoidMonolith39068 @ [69,51] (101 tiles) — SKIPPED (raid imminent, too far). Cave-builder visitor letter — visitor already left 2d 4h, both dismissed.
- Recreation variety alert: ChessTable blueprint at [126,133] (70 wood). Moods: Mila 60, Ace 52, Potts 57.
- Rice being harvested (Mila). Food 9.4 days, meals_all 45. Foraging stuck (no wild plants left nearby).
- "Need defenses" High still on: raid expected any day. No-trap policy holds (door lane = stockpile). Wood 1112 (surplus — consider lowering forestry to 500), steel 984, silver 800.

## Day 3, 17h — hare fight IN PROGRESS
- Hare41338 manhunter at [114,143] (19 tiles from home, HP 100% — pawns keep missing the fast hare). Ace (78%, minor blood loss, mood 45) + Mila both drafted & shooting; Potts cooking (fine).
- Plan: let combat order finish it. If hare still active at next wake: escalate (Mila melee, or accept loss and release — it is a small threat, not worth chasing forever).
- Ace needs tending (minor blood loss) — rescue order should handle post-fight (Mila Medicine 8).
- Mad hare letter dismissed. Chess table still blueprint. Batteries ~25%+ by now.

## Day 3, 18h — hare escalation
- Mila ordered MELEE on the hare (was 4.5 tiles, pawns kept missing at range). Ace job cancelled (was 51% HP, major blood loss risk from endless bites); still drafted, "watching for targets".
- Expect: Mila kills hare in ~7 knife hits, takes a few bites (minor). Post-fight: rescue order should tend Ace (Mila Med 8). CHECK at next wake: hare gone? Ace tended? moods recovering?
- If hare somehow still alive at next wake: it gives up on its own eventually; do not chase.

## Day 3, 18h+ — hare DEAD (Mila melee). Danger None.
- Ace: 40% HP, ~19 untended bite wounds (major 3.7-4.0, 3.2 HP/day total bleed) — downed; Potts rescuing him to Bed39786 @ [126,139] which I toggled MEDICAL.
- Mila: 95%, 1 bite (sev 3.77, bleeding, left arm); undrafted by me (combat order will not re-draft, no hostiles).
- Posture "cookresearch" refreshed 24h: Patient +1.0, Cooking +0.5, Research +0.5 (was missing Patient — all 3 had Patient 4, nobody would tend!).
- Outside stockpile now shows Corpse_Wolverine + Corpse_Hare + "2 forbidden" stacks + 1 dropped gun (WeaponsRanged) — check next scan; unforbid order covers home area only.
- Next check: tending started (Mila Med 8 -> Ace on med bed), batteries ~25%, moods (46 avg, Ace 38).
- Raid still pending ("Need defenses" High). No-trap policy holds.

## Day 3, 21:30 — priorities FIXED MANUALLY (scorer bug); 4th bed; medical OK
- All 3 pawns now MANUAL priorities (steward scorer zeroed Mila's matrix; re-hand-back only fixed Ace). Matrices: Mila {Cooking 1, Growing 1, PlantCutting 1, Research 3, Hauling 2, Doctor/Patient 2, Construction 3, Firefighter 2, Fishing 3, rest 4}; Potts {Research 1, Hauling 2, Cooking 2, Doctor/Patient 2, Construction 2, Growing/PlantCutting/Mining 3, Firefighter 2, rest 4}; Ace {Patient/PatientBedRest 1, Research 3, rest 4}.
- **RAID PROTOCOL (manual!): combat order no longer auto-drafts anyone (all unmanaged). On hostile_group: rw_ui_draft Ace (rifle) + Mila (revolver), push to rally [120,132,10,9], Potts (unarmed) stays inside/cooks.**
- 4th bed blueprint [124,139] rot E (45 wood, id Blueprint_Bed42492) -> clears "Need colonist beds" + "1 colonist without a free bed".
- Ace 44% HP on MEDICAL bed Bed39786 [126,139]; 3 medkits used, wounds bandaged ("tendable now: no"); sleeping, mood 39. Mila's bite (sev 3.77) still untended -> Potts (Doctor 2) should tend it tomorrow.
- Batteries ~24%; Potts Research 1 from day4 6h (schedule wakes 6h).
- Only forbidden thing left on map: wolverine corpse [45,84] (97 tiles, fresh) — leaving it; no hauler trip worth it.
- NO WILD ANIMALS on map (only cat Adrian) — hunting/foraging jobs stalled until animals respawn.
- Posture "cookresearch" still on timer but INERT (no managed pawns). Expires ~day4 17h.
- Chess table blueprint still pending (Potts Construction 2 will build it).

## Day 4, 9h — recovering; research resumed; cat dead
- Batteries 27% (Potts researching since 6h — manual matrix fix WORKS). Mila cooking (mood 61). Ace 49% HP on med bed, mood 48, fed, ALL wounds tended (0 untended). Starvation + break-risk alerts cleared.
- Cat Adrian torn to death (letter 3 dismissed; likely the wolverine that passed ~8h — danger Low->None). Pet-died mood thoughts pending on Mila/Potts.
- RawRice not yet in stockpile: Mila harvested 6h; 2 raw-plant stacks outside stockpile (PlantFoodRaw:2) — Hauling 2 (Potts/Mila) will haul. Food 8.6 days.
- Blueprints 2 pending (4th bed [124,139], chess table [126,133]) — unbuilt yet (Potts researching, Mila cooking; Construction 2-3 will queue them later today). "Need colonist beds" alert persists (count-quirk: med bed not counted + Ace's assignment released) but all 3 have beds tonight.
- Wood 1190, steel 984. Hunting/foraging still stalled (animals/plants respawning; +1 guinea pig meat appeared).
- Next check (13h): research ~35%+, bed/chess built?, rice hauled?, moods post-pet-death, Ace ~55%+.
- Raid protocol unchanged: manual draft Ace(rifle)+Mila(revolver) on hostile_group.
