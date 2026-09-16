# Colony notebook, episode 3 (sandbox/god mode)

## State
- 21 colonists (Hyena + 20 spawned: Snyder, Doctor, Anatoly, Galli, Mayer, Braddock, Belle, Wex, Amaya, Ross, Draper, Jackalope, Moss, Lady, Tuomi, Vedat, Valerie, Wilson, Soda, Morty). All healthy, mood ~45.
- Day 8 spring, food_days 1.2 (rice harvest in 0.4 days + 80 survival packs spawned → self-corrects).
- 49 mini-turrets: 25 powered on net 4 (2000W gen = 2000W load, 0 net gain), 24 on unpowered nets. 2 new generators on isolated nets 8/9 (not wired to net 4).
- 20+ beds spawned in grid [120-140, 155-161].
- 100 corpses destroyed (destroy_corpses tool).
- Food policy set to Lavish on all 21.
- 50 medicine spawned.

## Hyena catharsis crash
Hyena at 34% mood with +40 catharsis fading → post-fade ~-6% (below major 20%).
Permanent debuffs: MyDaughterLost -20, MySonDied -20, PawnWithGoodOpinionDied -10, WitnessedDeathFamily -6, WitnessedDeathAlly -5, SleptInCold -4, SleptOutside -4, IdeoBuildingMissing -4.
Total permanent: -73. This colonist is a mood liability in any colony. In sandbox, accept the crash.

## Learnings this step
- Turret draw is 80W each (NOT 400W). 49 turrets = 3920W > 2000W gen, so only 25 powered.
- New generators spawned via dev.spawn land on isolated nets (no auto-connect to existing conduit). Must wire manually or place adjacent to existing conduit.
- food_policy_set tool: all 21 colonists had null policy (unknown_policy=true) → set to Lavish in one call.
- destroy_corpses: 2 calls of 50 each = 100 corpses cleared.

## Next experiments
- Wire the 2 new generators to net 4 (add conduits) so battery charges.
- Build a proper roofed bedroom for Hyena (she's at mood 0-47, family-loss thoughts are permanent).
- Test: does adding a 3rd generator to net 4 push net_gain_w > 0?
- Try rw_dev_incident to test raid response with 25 turrets.
