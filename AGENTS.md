# rimagent, developer notes (agent-readable)

Two halves in one repo:
- `mod/` **RimBridge** (C#, RimWorld 1.6, Harmony): loopback HTTP bridge exposing the engine. Symlinked into the
  RimWorld Mods folder as `RimBridge`. Build `script/build.sh` (needs `DOTNET_ROOT=/opt/homebrew/opt/dotnet/libexec`),
  then `script/restart-game.sh` (DLLs load at startup only; always launch via Steam so Workshop Harmony loads).
- `agent/` **rimagent** (Python, uv): the brain. `script/start.sh` = launch game if needed + `rimagent play` + dashboard.
- `brain/` what the agent authors: `skills/*.md` (frontmatter name/description/tags/always), `tools/*.py`,
  `watchers/*.py` (hot-loaded), `memory/notebook.md` (per colony), `memory/journal.md` (cross-game), `scores.jsonl`.
  The runner commits `brain/` per episode; the agent can `brain_revert`.
- `knowledge/` wiki dump + BM25 (`rimagent seed`), `source-1.6/` (ilspycmd of the installed DLL), `source-legacy/`.

## Bridge
`POST 127.0.0.1:8765/rpc {"method":"state.summary","params":{}}`; `GET /health /methods /events?since= /screenshot?x=&z=&w=`.
Method groups: game.* state.* map.* ui.* engine.* defs.* dev.* steward.*, see `[Rpc(name, doc)]` attributes in `mod/Source`.
All Verse work runs on the main thread via `MainThreadQueue` (drained in a `Root.Update` postfix); request threads
only parse/serialize. Never throw into Unity: every RPC error becomes `{ok:false,error}`. Namespaces `GameCtl`/`MapView`
avoid clashes with `Verse.Game`/`Verse.Map`.
- **Steward** (`steward.*`, `mod/Source/Steward/`, namespace `RimBridge.Steward`): two vendored engines that run every tick
  without the LLM. `Scorer/` (Free Will port, MIT) writes work priorities for every *managed* colonist; `Stock/` (synchronous
  rewrite of Colony Manager Redux, MIT) keeps stock jobs (forestry, foraging, hunting, mining, production, livestock) at
  targets by designating work; `StewardRpc.cs` exposes status/enable/pawn/explain/posture/stock.*/settings/research,
  `StewardTuning.cs` holds posture deltas and the per-pawn managed gate, `StewardLedger.cs` emits `stock_stalled` /
  `stock_reached` / `posture_expired`. Both default ON and survive save/load. Rule: `ui.set_work` marks the pawn
  unmanaged before applying and returns `steward_managed: false` (otherwise the scorer would clobber the change);
  `steward.pawn managed=true` hands the pawn back. Nothing in steward.* marks the game assisted. Origins in
  `THIRD_PARTY_NOTICES.md`; keep vendored headers, add "modified for RimBridge" lines.
- **Orders** (`steward.orders*`, `mod/Source/Steward/Orders/`): standing orders are deterministic reflexes that run from a
  MapComponentTick, staggered by id, never throw, budget-logged over 20 ms: `combat` (draft capable fighters to the rally
  rect, hold, release, then rescue), `rescue`, `unforbid`, `corpses`, `beds`, `policies`, `blueprints`, `fire`. One class per
  order (`Order_*.cs`, base `Order { Id, Label, Doc, IntervalTicks, Enabled, Run(Map) -> OrderReport, Explain() }`), registry
  and persisted state (enabled flags, rally rect, manual-touch cooldowns, last summary) in `StandingOrders.cs`, RPCs in
  `OrdersRpc.cs` (`steward.orders`, `.set`, `.rally`, `.explain`, `.run`). Manual-touch rule: `ui.draft/goto/attack`,
  forbid/unforbid, `ui.set_policies`, `ui.press` on a bed and `ui.job Rescue/TendPatient` record (id, tick) so the matching
  order skips that pawn/thing for a cooldown. Ledger kind `orders` (`combat_engaged`, `combat_released`, `rescue`, `corpses`,
  `blueprints_cancelled`, `fire`). The brain watchers that did the same from Python stay, but the runner marks them *superseded* (`registry.watcher_superseded`,
  table `watchers.SUPERSEDED_WATCHERS`, config `steward.orders.superseded_watchers`) and `watchers.run_all` skips them while
  their order is on and the mod answered `steward.orders.set`: their `ui.draft/goto/order/designate` calls would record manual
  touches that pause the order for the very pawns they move. `watcher_write`/`watcher_delete` lift the mark; the seeded
  doctrine tells the director to delete them.

## Agent
- `rimagent play [--max-days N] [--seeds a,b] [--no-pause] -v`, `rimagent think` (one step), `rimagent tools`, `rimagent llm "hi"`, `rimagent seed [--distill]`.
- Bridge methods auto-become tools `rw_<group>_<name>`; models send JSON args as strings → `registry.coerce_param`.
- Think step = fresh bounded conversation (`loop.think`), ends with `end_turn`/`end_episode`. Runner (`runner.py`) pauses
  the game while thinking, wakes on schedule / ledger event kinds / watcher alerts, autosaves daily, runs an improvement
  pass every N days and an episode reflection at the end, then starts the next seeded game.
- Dashboard `127.0.0.1:8770` streams `bus.py` events (see its docstring for the event contract).
- Tests: `cd agent && uv run pytest -q`; `cd mod/Tests && dotnet test` (PathParser only; keep it Verse-free).

## Conventions
- Log from C# via `BridgeLog` (`[RimBridge]` prefix). Watch `~/Library/Logs/Ludeon Studios/RimWorld by Ludeon Studios/Player.log`.
- Tool results are truncated (~8k chars); prefer narrow queries in tools and docs.
- Config: `config.yaml` (generic) + `config.local.yaml` (gitignored: your LLM endpoint). Seeds, cadence, speeds live there.
  `steward: {enabled, scorer, stock, orders: {enabled, off: [], superseded_watchers?: {stem: order id}}}` (all default true): the runner calls `steward.enable` and
  `steward.orders.set` at new_game/recover_game and when the dashboard toggles it; the situation packet gets a "Steward"
  block from `steward.status` (posture, stock rows, problems, orders line, `rally: none` when unset).
