# agentv2

agentv2 plays RimWorld through the RimBridge mod and improves its own brain between and during games. It is a new
agent, built from the start on [Pydantic AI](https://pydantic.dev/docs/ai/overview/) and
[Pydantic AI Harness](https://pydantic.dev/docs/ai/harness/). The v1 agent in `../agent` is not used.

## Run

```bash
cd agentv2
uv sync
uv run agentv2 llm "hello"          # check the model endpoint
uv run agentv2 tools                # list the director's tools (no game, no model)
uv run agentv2 fake -v              # play an in-process fake game: no RimWorld needed
uv run agentv2 play -v              # play RimWorld through RimBridge (the mod must be loaded)
uv run pytest -q                    # tests (scripted model and fake game; no network)
```

The dashboard is at http://127.0.0.1:8771. Set `dashboard.host: 0.0.0.0` to serve it on the LAN; it has no authentication.

Configuration: `config.yaml`, then `config.local.yaml` (gitignored), then the variables `AGENTV2_LLM_BASE_URL`,
`AGENTV2_LLM_MODEL`, `AGENTV2_LLM_API_KEY` and `AGENTV2_BRIDGE_URL`.

## The model

Any OpenAI-compatible Chat Completions server (the default is the local sglang server with Qwen). agentv2 sends no
sampling or thinking parameters: the server defaults apply. Reasoning text (`reasoning_content`) arrives as Pydantic AI
`ThinkingPart`s and streams to the dashboard. The only model setting is the profile flag
`openai_chat_supports_multiple_system_messages=False`, because the Qwen chat template accepts one system message only.

## Architecture

One asyncio loop runs everything: the game poller, the watchers, the think steps, the brain passes and the dashboard.
`runtime.py` builds every part once; the CLI and the tests use it.

- **Director** (`director.py`, prompts in `roles.py`): the agent that plays. One game is one continuous conversation, kept
  by `StepPersistence`: each step reads it back from `runs/steps.sqlite`, so the next step continues after a failed or
  cancelled step and after a restart. Each wake-up adds a situation report (`situation.py`) as a new user turn; the step
  ends with the output tool `end_turn` (a wake plan) or `end_episode`. Urgent events and operator messages that arrive
  during a step go into the running step (`AgentRun.enqueue`); "end episode" and "kill" cancel it (`AgentRun.cancel`).
- **Improver and reflector** (`passes.py`): the same brain and tools, but they only read the game, and they can search the
  director's whole conversation (`search_conversation_history`). The improver runs every few in-game days beside the
  director; the reflector runs when a game ends. The brain is committed to git after each pass.
- **Runner** (`runner.py`): starts or resumes games, wakes the director (`wake.py`: schedule, ledger events, game alerts,
  watcher alerts), sets the game speed while thinking (`game.py`), autosaves, scores. `poller.py` reads the ledger and runs
  the watchers all the time; `episode.py` keeps the episode (tallies, timeline, pass notes) in `runs/episode.json`.
- **Dashboard** (`dashboard/`): reads the bus (`bus.py`; one model per event kind in `events.py`) and the brain
  (`brain_view.py`), and changes only what `controls.py` offers.

| Piece | Built with |
|---|---|
| RimBridge methods as tools `rw_<group>_<name>` | a custom `AbstractToolset`; typed JSON schemas parsed from the method docs (`catalog.py`), a parameter named like a Python keyword gets a trailing `_`; bridge errors become `ToolFailed` |
| Who may call which method (`policy.py`) | core `PrepareTools` hides the `rw_*` tools a role may not use; it runs inside `CodeMode`, so `run_code` does not get them either |
| Tool arguments | Harness `RepairToolArguments` (broken JSON), then `CoerceArguments` (JSON inside string arguments) |
| Tool calls | Harness `CodeMode` (the Monty sandbox): every tool except `load_capability` and `author_capability` is a function in `run_code`, so the model composes calls in code. `SandboxCalls` shows each call from the code on the dashboard under its `run_code` call. `ToolOutputLimits` skips calls from the code, so the code gets whole results |
| Map screenshots | `look` returns `[mark table, marked PNG as BinaryContent]`; a `run_code` snippet that ends with it gives the model the image |
| Doctrine (`brain/AGENTS.md`) | Harness `RepoContext` |
| Skills (`brain/skills/<name>/SKILL.md`) | Harness `Skills`, loaded on demand with `load_capability`; re-read every run through core `DynamicCapability` |
| Notebook (per colony) and journal (across games) | two Harness `Memory` capabilities on one `FileStore` |
| Tools the agent writes for itself | Harness `CapabilityCreation` (`brain/capabilities/`), active from the next run, tools prefixed `my_`; a run that they break runs again without them |
| Editing the brain | Harness `FileSystem` on `brain/` (tools prefixed `brain_`) |
| RimWorld wiki and decompiled source | Harness `FileSystem`, read-only, on `../knowledge` (tools prefixed `kb_`), when it exists |
| Watchers (reflexes without the model) | agent-written scripts run in the Monty sandbox (`watchers/`) |
| Large tool results | Harness `ToolOutputLimits` (spill to disk, page with `read_tool_result`) |
| Long games | Harness `TieredCompaction` (clear old tool results, then summarize), `ReportContextUsage`, `StepPersistence` |
| Recall in the brain passes | Harness `ConversationSearch` over the director's `StepPersistence` snapshots |
| Step budget | `WarnNearLimits` plus `StepBudget`: after `max_requests` requests only `end_turn` is offered |
| Live transcript | core `ProcessEventStream` forwards each run's events to the bus (`capabilities/telemetry.py`) |
| Brain history | `score_history`, `brain_log`, `brain_diff`, `brain_revert`, `delete_skill`, `delete_watcher` |

## The brain

```
brain/
  AGENTS.md                 doctrine: priorities, routine, the RimBridge manual; loaded into every step
  skills/<name>/SKILL.md    frontmatter `name` (= folder name) and `description`, then the Markdown body
  watchers/<name>.py        reflexes (below)
  capabilities/             agent-authored capabilities and manifest.json
  memory/                   Memory FileStore: <colony>/main/MEMORY.md (notebook), journal/MEMORY.md
  operator.md               what the human operator said
  scores.jsonl              one row per episode
```

The seed brain comes from v1: ten strategy skills, the doctrine and the bridge manual (merged into `AGENTS.md`), the
journal, and four watchers rewritten for the sandbox.

## Watchers

A watcher is `brain/watchers/<name>.py` with one function:

```python
async def watch(events, status, memo):
    out = []
    for e in events:
        if e["kind"] == "hostile_group":
            out.append({"type": "action", "method": "game.speed", "params": {"speed": 1}, "note": "raid"})
            out.append({"type": "alert", "text": "RAID: " + e.get("text", ""), "wake": True})
    return out
```

It runs in the Monty sandbox on every new ledger event and at least every `watchers.poll_s` seconds: no host files, no
imports beyond Monty's subset, one second per call. `memo` persists between calls. `await rpc(method, params)` reads the
game (read-only methods only). The runner executes returned actions and logs them. A failing watcher, or one that returns
an item that is not an action or an alert, is disabled until its file changes. `test_watcher` dry-runs one.

## Not in agentv2

The v1 watchdog (source self-repair), the parallel specialist streams, the SFT capture and export, and the v1 tracker
and world diff are not ported.
