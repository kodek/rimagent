# Colony notebook, episode 1, seed rimagent-1

(new game; nothing decided yet)

Day 0, 6 Aprimay 5500. Crashlanded, temperate forest, spring, home_center ~[127,110].
Colonists: Bat (Human570) Con 8!!/Plants 7!! - rifle; Kalie (Human573) Social 9!!/Med 7!!/Craft 5!! - INCAPABLE OF VIOLENCE, no weapon; Josephine (Human576) Art 14!!/Melee 13!! - plasteel knife.
Done: main stockpile [119,106,9,6] (~54 cells, N of camp); rice1 growing zone [128,112,8,7] (56 cells) + rice crop; unforbid rect [116,102,16,14] (0 applied, drops were already unforbid); equipped rifle/knife; campfire built at [128,103]; stool x2 + table(2x2c) + simple research bench blueprints at z100-103; forestry target raised to 800, posture "day0 build" (Con +0.5) for 24h; research queue: Batteries (current) then SolarPanels.
SUSPECT: the two `room()` calls for the shelter (walls rect [119,97,11,9] wood, door at [124,97], beds [120,98],[120,100],[120,102]) reported "placed" with no failures but the 'alert: Need colonist beds' fired and no walls appear in map_view(buildings) - VERIFY with rw_map_find(kind=building, def="Wall") and rw_map_find(kind=blueprint) next step. If absent, rebuild with rw_ui_build_many.
Locations: loose steel/wood pile at [129,96]-[133,92] (~111 steel, 150 wood); more steel [177,75-78] (~211), [82,164] (~201), [235,232] (~104); survival meals at [35,17] and [119,222] forbidden.
Alerts: need beds (High), need recreation variety (Med), need research bench (Med).
Next: finish shelter, beds, then stone walls / defenses, foraging+hunting stock, cook bill on campfire.

Day 1 15h: shelter is UP but the ROOM IS NOT ENCLOSED YET - door at [124,97] built, north door at [124,105] still a frame, so beds/campfire count as "outside" (Kalie slept outside+on ground+in cold, -12 mood, mood 45). Posture "shelter up" (Construction +0.6, Hauling -0.4) for 16h to finish the frame. Beds built at [120,98]/[120,100]/[120,102] rot E, owned by Bat/Kalie/Josephine; campfire [128,103], table+2 stools [123-126,100], research bench [124,103], horseshoes pin [133,102]. Rally set [121,99,6,4]. Wood 420, steel 413, meals 41, food_days 8.9. Research queue: Batteries(current) > SolarPanels > Pemmican > Smithing. NEXT: confirm room enclosed (room_digest shows a real room, no "furniture not in room"), then build separate bedrooms / outer wall + killbox before day 5 raid.

Automation pass (day 1): added tool `step_brief` (one call -> date/food_days/mood/blueprints+frames/alerts/designations/rooms/key_stocks with a notes verdict) and watcher `shelter_guard` (wakes me on "slept outside/on ground/in the cold" or "needs a bed" ledger lines — the half-finished-shelter trap). Tightened base-building skill: verify enclosure from state (room_digest shows Barracks + temp, blueprints==0 and frames==0), never from the build result; day-0 crashlanded shelter that worked = wood walls [119,97,11,9], door (124,97), 3 beds, interior 63 cells, temp 28C.
