# rimagent

**An LLM that plays RimWorld and rewrites its own playbook between colonies.**

A local model (tested with Qwen 3 27–32B on vLLM) runs a RimWorld colony through a mod that exposes the whole engine over HTTP. It sees the world as objects, trends and diffs rather than pixels or grids, controls the game with the same verbs a player has (right-click orders, gizmos, designators, blueprints, zones, dialogs, trade), and keeps everything it learns on disk: **skills** (markdown), **tools** and **watchers** (Python, hot-loaded), a journal, and a score per episode. Every colony ends in a reflection that edits those files and commits them. Then it starts the next one.

<p align="center"><a href="docs/PAPER.md"><b>Read the paper</b></a> · <a href="https://github.com/zorrobyte/rimagent/releases/latest">Download the mod</a> · <a href="#quick-start">Quick start</a></p>

<p align="center"><img src="docs/dashboard-live.png" width="900" alt="Live dashboard: tracked trends, what changed, and a think step"></p>

## What it looks like

| The base as the model sees it | Set-of-Mark screenshot (`look`) |
|---|---|
| <img src="docs/dashboard-base.png" width="440"> | <img src="docs/map-compound.png" width="440"> |

The *building camera*: every column is numbered, each building type gets its own letter (lowercase = blueprint), and `*` marks an interaction spot that must stay clear.

```
      111111111111111111111111111111111111
      334444444444555555555566666666667777
      890123456789012345678901234567890123
 123  ..AAAAAAA+AAAAAAAAAAAAAAAT..........
 121  ..A....T.JJ..KT.A..LLL..A...........
 120  ..A.....HJJH.*..+......T+...........
 118  ..A.............A..GGG..A...........
 116  iiAAAA+AAAAAA+AAAAAA+AAAA..FDD......
 115  ..A.C....A.C...TAi.T....A...DD....T.
 110  ..AAAAAAAAAAAAAAA.......A.........T.
 109  T........T......AABAAABAA.......T..T
```
`A` walls · `B` coolers (in the freezer wall) · `C` beds · `D` generator · `F` battery · `G` butcher table · `H` chairs · `J` table · `K` campfire · `L` stove · `+` doors

The compound above was laid out through the same tools the model uses, with named anchors instead of coordinates:

```
rw_anchor_set(name="hall", rect=[140,116,15,8])
rw_ui_build_many(ops=[
  {"def":"Door","stuff":"Steel","at":"hall:N"},
  {"def":"Cooler","at":"freezer:S +W2","rot":"N"},
  {"def":"Wall","stuff":"Steel","rect":"hall"},
  {"def":"Bed","stuff":"WoodLog","at":"bed1:inset:1:NW +E1 +S1","rot":"N"},
  {"def":"FueledStove","at":"kitchen:inset:2:NW +E2","rot":"S"}])
```

## How it works

```mermaid
flowchart LR
  subgraph game["RimWorld (Unity)"]
    RB["RimBridge mod<br/>C# + Harmony"]
    E["engine objects<br/>maps, pawns, defs, windows"]
    L["event ledger<br/>letters, incidents, danger, deaths, dialogs"]
    C["off-screen camera"]
    RB --- E
    RB --- L
    RB --- C
  end
  subgraph agent["rimagent (Python)"]
    R["runner<br/>episodes, wake policy, speed"]
    T["think step<br/>bounded tool-use loop"]
    W["watchers<br/>reflexes, no LLM"]
    I["improve stream<br/>concurrent"]
    D["dashboard<br/>SSE, operator chat"]
    R --> T
    R --> W
    R --> I
    R --> D
  end
  subgraph brain["brain/ (git)"]
    S["skills/*.md"]
    TL["tools/*.py"]
    WT["watchers/*.py"]
    M["notebook, journal, scores"]
  end
  K["knowledge<br/>wiki index, decompiled source"]
  LLM["LLM<br/>OpenAI-compatible, tool calls, vision"]
  RB <-- "HTTP 127.0.0.1:8765" --> R
  T <--> LLM
  I <--> LLM
  T --> brain
  I --> brain
  brain -. hot-load .-> T
  brain -. hot-load .-> W
  K --> T
```

One think step, from wake to sleep:

```mermaid
sequenceDiagram
  participant G as RimBridge
  participant R as runner
  participant M as model
  participant B as brain/
  R->>G: poll ledger, run watchers
  Note over R: wake: schedule, critical event,<br/>critical alert, watcher, operator
  R->>G: pause (danger) or keep 3x (calm)
  R->>G: state.summary, state.base, dialogs, letters
  R->>R: tracked trends + world diff
  R->>M: situation packet + tools
  loop up to 30 tool calls
    M->>G: rw_* call (orders, build, engine.get, ...)
    G-->>M: result, or failure with a marked mini-map
    R-->>M: urgent events / operator messages injected mid-step
  end
  M->>B: notebook, skill_write, tool_write, watcher_write
  M->>R: end_turn(notes, wake_in_hours, wake_on)
  R->>G: restore speed (or the model's choice)
```

Between colonies:

```mermaid
flowchart LR
  P["play"] -->|"day 1, then every 3 days"| IP["improvement pass<br/>2nd LLM stream"]
  IP -->|"watchers, tools, skill edits"| C1["git commit brain/"]
  P -->|"colony lost / day cap / end_episode"| RF["episode reflection<br/>timeline, scores, operator tips"]
  RF -->|"skills, journal, revert if worse"| C2["git commit brain/"]
  C2 --> N["new seeded game"] --> P
```

**Perception (what a think step opens with):** tracked values with trends (`food_days 9→7→5 ↓`, add your own engine path with `watch_add`), a harness-computed diff of the world since the last step, the base as rooms/doors/contents/problems (`state.base`), events, alerts, letters, open dialogs, then the raw numbers. Grids and pictures are on demand: `map.detail` (building camera), `map.view` (layers), `look` (screenshot with grid + numbered marks + anchor boxes).

**Control:** float-menu orders and gizmos (exactly what a player can click), designators, blueprints with a location grammar (`Campfire39256 +E2`, `@Gamble`, `bedroom2:NW`, `bedroom2:extend:E:4`, `Room:12`), zones/areas/storage, work priorities, schedules, policies, bills, research, letters and every window type (rituals, trade, naming, message boxes; a generic reader/answerer for anything else). `engine.get/set/call` reach any live object by path for the rest; the decompiled source is searchable so the model can find the right API itself.

**Learning:** an improvement pass on a second LLM stream every few days (turn repeated reactions into watchers, repeated computations into tools, tighten skills with numbers), an episode reflection at the end, per-episode scores, git history of `brain/`, `brain_revert` when a change made things worse. Tips you type in the dashboard are folded into skills.

**Knowledge:** the RimWorld wiki (scraped, BM25) and the decompiled game source (`search_source`, `read_source`). It reads the actual raid-point formula rather than guessing it.

## Quick start

Requirements: RimWorld 1.6 (tested on macOS/Steam with all DLCs), [Harmony](https://steamcommunity.com/sharedfiles/filedetails/?id=2009463077), .NET SDK 8+, [uv](https://docs.astral.sh/uv/), `rg` (ripgrep), and an OpenAI-compatible endpoint with native tool calls (vLLM: `--enable-auto-tool-choice --tool-call-parser hermes`; vision optional).

```bash
git clone https://github.com/zorrobyte/rimagent && cd rimagent
ln -s "$PWD/mod" "$HOME/Library/Application Support/Steam/steamapps/common/RimWorld/RimWorldMac.app/Mods/RimBridge"   # macOS path
script/build.sh                          # builds mod/1.6/Assemblies/RimBridge.dll
cd agent && uv sync && cd ..
cp config.yaml config.local.yaml         # put your llm.base_url / model in config.local.yaml
cd agent && uv run rimagent seed         # wiki → knowledge/wiki + BM25 (~10 min); decompile optional, see below
cd .. && script/start.sh                 # launches RimWorld via Steam if needed, starts the agent, opens the dashboard
```

Enable `RimBridge` in the mod list (after Harmony) the first time. The dashboard at http://127.0.0.1:8770 has tabs for Live (steps, the situation the model was shown, chat with the agent), Ledger, Watchers, Brain (skills, tools, watchers, memory, git history), Scores, Base, Map and ASCII.

Optional: decompile your own `Assembly-CSharp.dll` into `knowledge/source-1.6/` with [ilspycmd](https://github.com/icsharpcode/ILSpy) so the model can read the exact game code (`dotnet tool install -g ilspycmd; ilspycmd -p -o knowledge/source-1.6 <path to Assembly-CSharp.dll>`). Decompiled source is not part of this repo.

Useful commands: `rimagent think` (one step against the live game), `rimagent tools`, `rimagent llm "hi"`, `script/reload.sh` (save → restart game with a rebuilt mod → load → resume the agent), `curl localhost:8765/methods`.

## Repo layout

- `mod/`: RimBridge (C#). `Source/Engine` holds reflection and the location grammar, `State` the summaries and scene graph, `Map` the ASCII views, camera and screenshots, `Ui` the player-parity controls and dialogs, `Ledger` the Harmony event patches, `Dev` the training tools. `mod/Tests` (xunit) covers the pure parser.
- `agent/rimagent/`: runner, loop, registry (hot-loading tools and watchers), tracker, worlddiff, annotate (Set-of-Mark), reflect, skills/memory/scorecard, dashboard, knowledge (wiki and source), prompts.
- `brain/`: everything the agent authors. It starts with 13 seeded skills: the doctrine, the bridge manual, ten wiki-distilled strategy skills, and a worked base example.
- `docs/`: screenshots and the paper (`PAPER.md`).

## Status

Early and very much alive: it loses colonies (fires, mech clusters, starvation), reflects, and comes back with new watchers and tighter skills. Cold-start play quality is not the point; the slope is. Contributions that make the *harness* see or act more faithfully are welcome; game strategy belongs in `brain/`, written by the agent.

## Paper

The design, the interface defects found by watching the agent play, and preliminary results from three colonies are written up in [docs/PAPER.md](docs/PAPER.md): *RimBridge and rimagent: A Player-Parity Interface and a Self-Editing Brain for Language-Model Agents in RimWorld* (preprint, September 2026). If you build on it:

```bibtex
@misc{rimagent2026,
  title  = {RimBridge and rimagent: A Player-Parity Interface and a Self-Editing Brain for Language-Model Agents in RimWorld},
  author = {zorrobyte},
  year   = {2026},
  url    = {https://github.com/zorrobyte/rimagent}
}
```

## License

MIT. RimWorld is © Ludeon Studios; this project is an unofficial mod + agent and ships no game assets.
