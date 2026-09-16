# Journal, lessons that survive between games


## 2026-09-16 18:37 (episode 1): StrangerInBlack can join and save a dying colony
A StrangerInBlack (faction "Player", e.g. "Chris" with high Medicine/Shooting) can appear mid-game and immediately tend a downed colonist. When a colony is down to 1 bleeding colonist, check state.pawns filter=colonists for a StrangerInBlack before declaring it lost — they may be the medic who carries you through. They are counted as colonists and can fight. Do not assume "last able colonist" means "alone" without checking the pawns list.

## 2026-09-16 18:39 (episode 1): Manhunter response: run to base, don't intercept
When a manhunter (rat, wolf, etc.) is chasing a colonist far from base: order the chased colonist to run TO BASE immediately (rw_ui_goto to base center). Do NOT send a second colonist to intercept the manhunter far away — both get downed 70+ cells from base and the colony collapses. A manhunter loses interest after 30-50 cells of failed chase. If the manhunter is 50+ cells from base it is not an immediate base threat; it is a threat to the specific colonist it is chasing. If a colonist is already downed far from base and the rescuer is bleeding or below 50% health, the rescue will likely kill the rescuer too — accept the loss and keep the last able colonist alive.

## 2026-09-16 18:39 (episode 1): Turrets are a day-1-2 priority, not a day-10 luxury
Crashlanded loot has ~1,450 steel and ~28 components. A wood-fired generator (100 steel + 2 components) + battery (70 steel + 2 components) + 2 mini-turrets (140 steel + 6 components) totals ~400 steel + 8 components — well within day-1 loot. Without turrets, a 3-colonist colony has no automated defense against anything beyond 2-3 raiders. Build turrets BEFORE the first raid (~day 5-10 on Rough). The defName is Turret_MiniTurret (not Turret_Gun).
