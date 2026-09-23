# Plan: migrate rimagent to Pydantic AI

Date: 2026-09-22. Status: proposal. Scope: `agent/rimagent/**` only.

This plan uses ASD-STE100 Simplified Technical English. Code names stay in their original form.

## 1. Summary

rimagent has no agent framework today. It calls the `openai` SDK directly and has a hand-written tool loop. This plan replaces the model layer, the tool loop, the retry logic, the test doubles, and the fan-out with Pydantic AI. It keeps the parts that are specific to rimagent: the brain, the watchers, the bridge, the situation packet, and the watchdog guardrails.

The main decisions:

1. Use `OpenAIChatModel` with `VLLMProvider`, and give it your own `AsyncOpenAI` client. This keeps the current wire behavior: no SDK retries, 240 s timeout, `extra_body` thinking switch.
2. Run all model calls on one event loop in one dedicated thread. The runner stays synchronous. A shared async client across threads fails (a research agent reproduced this failure).
3. Make one `Agent` per role. A think step is one `agent.run(...)`. `end_turn`, `end_episode` and `end_watchdog` become output functions.
4. Expose the existing tool registry to Pydantic AI through one custom toolset. The brain tool API (`@tool`, `fn(ctx, ...)`) does not change.
5. Feed the dashboard bus from non-streaming capability hooks. Do not use event listeners, because they switch model requests to streaming.
6. Capture SFT data at the HTTP layer with `httpx2` event hooks. This keeps the capture wire-exact, so `export_sft.py` changes little.
7. Use Pydantic AI Harness only in an optional, later phase. It is 0.x alpha and releases a breaking minor version every few days.

## 2. Sources and versions

| Item | Version read | Notes |
|---|---|---|
| `pydantic-ai-slim` | main `6f86c95`, release 2.47.0 (2026-09-22) | V2 is stable since 2026-06-23. The next major release comes 3 months after V2.0 at the earliest. |
| `pydantic-ai-harness` | main `e179755`, release 0.33.0 (2026-09-22) | "Development Status 3 - Alpha". 38 releases in 5 months. Needs `pydantic-ai-slim>=2.44.0`. Has no `openai` extra. |
| rimagent | main `85cb050` | `uv.lock` already has `openai 3.14.1`. Pydantic AI needs `openai>=3.8`, so there is no conflict. |

All 252 Pydantic AI doc pages and all Harness doc pages were read. The research agents checked unclear points in the source and ran small probes.

## 3. Constraints

These things must stay true after the migration.

| Id | Constraint | Why |
|---|---|---|
| C1 | The brain tool API stays: `from rimagent.registry import tool`, `@tool(name, description, params, group=...)`, `fn(ctx, ...)` where `ctx` is the rimagent `Context`. | The agent writes `brain/tools/*.py` against this API. The prompts and the seeded tools document it. |
| C2 | Watchers stay outside the LLM loop. | They are reflexes. They must not wait for a model. |
| C3 | The bus event contract in `bus.py` stays. | The dashboard and `watchdog.recent_errors` read it. |
| C4 | The SFT capture record stays compatible with `export_sft.py`. | Existing captures and the export must keep working. |
| C5 | Watchdog guardrails stay in the tool bodies (`safe_path`, proof gate, commit rules). | They are server-side proof. A model that ignores its prompt must still be stopped. |
| C6 | Wire parity with vLLM: Chat Completions, `chat_template_kwargs.enable_thinking`, no reasoning sent back, `max_tokens`, no `strict`, no SDK retries, 240 s timeout, at most 4 concurrent requests. | These settings are tested on the real Qwen3 server. |
| C7 | Model requests stay non-streaming. | The vLLM streaming tool-call parser is a different code path. It is not tested with rimagent. |
| C8 | The runner stays synchronous. The game is external state. | A game action cannot replay. Durable execution does not fit. |
| C9 | The think-step semantics stay: a tool budget, then only the end tools; a nudge when the model writes text with no tool call; urgent events and operator messages that arrive mid-step. | The play quality depends on them. |

## 4. Feature map

Decision key: **Adopt** = use the library feature as it is. **Adapt** = use the library feature with a small rimagent part. **Keep** = keep the rimagent code. **Skip** = do not use. **Later** = optional, in Phase 6 or 7.

### 4.1 Model layer

| rimagent feature | Current code | Pydantic AI feature | Decision | Notes |
|---|---|---|---|---|
| OpenAI-compatible client | `llm.LLM`, sync `OpenAI` | `OpenAIChatModel` + `VLLMProvider(openai_client=AsyncOpenAI(max_retries=0, timeout=240))` | Adopt | Do not use the `openai:` prefix. In V2 it means the Responses API. |
| Profile for Qwen3 on vLLM | none | `OpenAIModelProfile` | Adopt | Set `openai_chat_send_back_thinking_parts=False`, `openai_chat_supports_max_completion_tokens=False`, `openai_supports_strict_tool_definition=False`. Set `context_window` to the vLLM `max_model_len`. |
| Thinking switch per call | `extra_body.chat_template_kwargs.enable_thinking` | `ModelSettings(extra_body=...)` | Adopt | Do not use the `Thinking` capability. It sends `reasoning_effort`. Older vLLM rejects `'none'`. `extra_body` merges are shallow, so send the full dict each time. |
| Read the reasoning text | `reasoning_content` or `reasoning` | `ThinkingPart`, automatic | Adopt | |
| Drop reasoning from history | `assistant_message` | profile `openai_chat_send_back_thinking_parts=False` | Adopt | |
| Retry once without thinking (empty reply or error) | `LLM.chat` recursion, `loop.think` attempt loop | custom `WrapperModel` | Adapt | About 25 lines. Add the first attempt's usage to the result. |
| Concurrency cap of 4 | `threading.Semaphore` | `ConcurrencyLimitedModel(limiter=4)` | Adopt | Works only inside one event loop. See section 5. |
| SFT capture | `LLM._capture`, `_tools_ref` | `httpx2.AsyncClient(event_hooks=...)` on the `AsyncOpenAI` client | Adapt | Wire-exact. Put episode, seed, stream and step in a `ContextVar` from a model-request hook. The hook reads it (verified in a probe). |
| Errors from the client | `openai.*` exceptions | `ModelHTTPError`, `ModelAPIError`, `UnexpectedModelBehavior` | Adopt | Catch these at the step boundary. |
| One-shot calls (`cli llm`, `seed.distill_skills`) | `LLM().chat` | `pydantic_ai.direct.model_request` on the loop service | Adopt | Pass a `Model` instance. A model string makes a new client each call. |

### 4.2 Think step

| rimagent feature | Current code | Pydantic AI feature | Decision | Notes |
|---|---|---|---|---|
| Bounded tool loop | `loop.think` | `Agent.run` | Adopt | `think()` keeps its signature and `StepResult`. Callers do not change. |
| System prompt | `build_system` | `run(instructions=...)` | Adopt | The text does not change. The vLLM profile merges leading system messages. |
| Situation packet | `situation_packet` | user prompt | Keep | Pure rimagent logic. |
| `end_turn`, `end_episode` | `ctx.stop_turn` flags | `output_type=[ToolOutput(end_turn), ToolOutput(end_episode)]` | Adopt | Tool hooks do not run for output tools. Coerce string arguments inside the output function. |
| Tool calls in the same response as `end_turn` | tools before `end_turn` run, tools after it are skipped | `end_strategy='graceful'` | Adopt | All co-emitted function tools run. `'early'` would skip the tools before `end_turn` too. Set the value explicitly. |
| Nudge when the model writes text only | two nudge messages | `output_type` without `str` makes Pydantic AI send `tool_choice='required'`; a text reply gets an output retry prompt | Adopt | Test `tool_choice='required'` with Qwen3 thinking on vLLM in Phase 0. If it fails, set `openai_supports_tool_choice_required=False`. The output retry prompt then acts as the nudge. |
| Tool budget (30), then end tools only | `max_calls` check | custom `StepBudget` capability: `prepare_tools` hides all function tools at the budget | Adapt | Add `UsageLimits(tool_calls_limit=2*max, request_limit=...)` as a hard stop only. `UsageLimits` raises. It does not end the step cleanly. The default `request_limit` is 50. Always set it. |
| History size guard (160k chars) | loop elides old tool results | `ProcessHistory` with the same rule | Adapt | Keep tool call and result pairs together. Harness `ClearToolResults` is a Later option. |
| Urgent events mid-step | `interrupt_check`, extra user message | hook after each tool batch + `ctx.enqueue(..., priority='asap')` | Adapt | `enqueue` is safe from hooks and other threads. Confirm the delivery timing in Phase 0. Do not use Harness `SystemReminders`: its text is seen on one request only. |
| Operator messages mid-step | `operator_inbox` | same as urgent events | Adapt | |
| Images from `look` | `_image_png_b64`, extra user message | `ToolReturn(return_value=..., content=[BinaryContent(png, 'image/png')])` | Adopt | Pydantic AI moves the image to the user channel for Chat Completions. The model must be a vision model. Qwen3-32B is text-only. This is true today too. |
| Bus events | `ctx.emit` in the loop | custom `BusEvents` capability on `before_run`, `after_model_request`, `wrap_tool_execute`, `on_tool_validate_error`, `after_run` | Adapt | Do not use `event_stream_handler`, `@on_event` or `ProcessEventStream`. Each of them switches requests to streaming (verified in `agent/abstract.py`). |
| Step cancellation | none | `CancellationToken` per run | Adopt | New. The runner can stop a step on shutdown. A sync tool thread is not stopped. Keep the bridge HTTP timeouts. |

### 4.3 Tools

| rimagent feature | Current code | Pydantic AI feature | Decision | Notes |
|---|---|---|---|---|
| Bridge tools `rw_<group>_<name>` from `/methods` | `registry.add_bridge_methods` | custom `RegistryToolset(AbstractToolset)` | Adapt | `get_tools` reads the live registry each step. `call_tool` calls the existing dispatch. |
| Built-in tools (brain, knowledge, meta, watchdog) | `@tool` + `registry.add_module` | same adapter | Keep | Later option: move them to typed `FunctionToolset` tools for real argument validation. |
| Hot-loaded brain tools | `reload_brain` (content digest) | same adapter; `get_tools` runs each step | Keep | A tool written in a step is callable in the next request of the same run. |
| Role allowlists and reserved groups | `roles.py`, `Registry.specs` | filter inside `RegistryToolset.get_tools` from `deps.role` | Keep | Filtering also blocks calls. Test the exact tool list per role with `FunctionModel`. |
| String-JSON argument coercion, alias remap | `coerce_param`, `remap_params` | none in core or Harness | Keep | Two agents verified that core does not coerce a JSON string to a dict or list. Harness `RepairToolArguments` repairs only malformed whole payloads. |
| Tool errors go back to the model as text | `execute` returns `{"error": ...}` | raise `ToolFailed(text)` | Adopt | `ToolFailed` does not use the retry budget. Any other exception ends the run. |
| Unknown tool name, bad arguments | `{"error": ...}` | automatic `ModelRetry` prompt | Adopt | The default tool retry budget is 1. Set `retries={'tools': 3, 'output': 2}`. Catch `UnexpectedModelBehavior` at the step boundary. |
| 8k-char truncation | `to_text` | keep in the adapter | Keep | Harness `ToolOutputLimits` is a Later option. |
| Parallel tool calls in one response | run in order, one at a time | run concurrently by default | Adapt | Set `parallel_tool_calls=False` in the model settings. UI actions must stay in order. |
| `run_python` | `tools/meta.py` | none | Keep | Harness `CodeMode` is a Later experiment for the play roles. |
| Knowledge search (BM25 wiki, decompiled source) | `tools/knowledge.py` | none | Keep | |

### 4.4 Orchestration and streams

| rimagent feature | Current code | Pydantic AI feature | Decision | Notes |
|---|---|---|---|---|
| Runner, wake policy, episodes | `runner.py` | none | Keep | |
| Parallel mode (4 specialist streams) | 4 threads, `join(timeout=900)` | `asyncio.gather` on the loop service, `anyio.fail_after(900)` | Adopt | One failed stream must not stop the others. Use `return_exceptions=True`. |
| Manager call | JSON parse of free text | `Agent(output_type=ManagerPlan)`, no tools, thinking off | Adopt | Keep the fallback: an empty plan when the call fails. |
| Improvement pass, episode reflection | `reflect.py` → `think()` | same agent factory | Adopt | |
| Watchdog pass | `watchdog.run_pass` → `think()` | watchdog `Agent`, `end_watchdog` as output function | Adopt | All gates stay in `tools/watchdog.py`. Harness `FileSystem` is a Later option. |
| Model-driven delegation | none | Harness `SubAgents`, `DynamicWorkflow` | Skip | The fan-out is host-driven. Model-driven fan-out adds risk with a 32B model. |
| `pydantic_graph` | none | `GraphBuilder` | Skip | It has no persistence. One failed branch cancels its siblings. `gather` is simpler. |
| Durable execution | autosave + `recover_game` | DBOS, Temporal, Prefect, Restate | Skip | The game cannot replay. A replayed step would give the model stale tool results. |

### 4.5 Memory, skills, and brain

| rimagent feature | Current code | Pydantic AI feature | Decision | Notes |
|---|---|---|---|---|
| Skills (BM25 top 4, `always`) | `skills.py` | Harness `Skills`; core on-demand `Capability(defer_loading=True)` | Keep | Harness `Skills` has no BM25 preselection and no `always`. It fails at construction on one bad agent-written file. On-demand loads cost one model round trip each. |
| Notebook and journal | `memory.py` | Harness `Memory` | Keep | `Memory` fixes the file name to `MEMORY.md`, puts a SQLite journal inside the git-committed `brain/`, and caps a file at 64k chars. |
| Brain git and `brain_revert` | `braingit.py` | none | Keep | |
| Watchers | `watchers.py` | none | Keep | Constraint C2. |
| Agent-written capabilities | none | Harness `CapabilityCreation` | Skip | The brain tool format already covers this need. |

### 4.6 Tests, observability, evaluation

| rimagent feature | Current code | Pydantic AI feature | Decision | Notes |
|---|---|---|---|---|
| Fake LLM in tests | `ScriptedLLM` in `test_watchdog.py` | `FunctionModel`, `TestModel` | Adopt | `FunctionModel` can script JSON-string arguments, empty replies and `end_turn`. `AgentInfo.function_tools` shows the tools that were offered. |
| Block real model calls in tests | none | `pydantic_ai.models.ALLOW_MODEL_REQUESTS = False` | Adopt | Set it in `conftest.py`. |
| Token usage | `reply.usage` per call | `result.usage` (`RunUsage`) | Adopt | Harness `SpendLimits` token counters are a Later option. Local models have no price, so use token budgets only. |
| Tracing | none | `Instrumentation` capability, OpenTelemetry | Later | Local only: an OTLP exporter or an in-process span processor. No Logfire account is necessary. |
| Regression evaluation | none | `pydantic_evals` `Dataset`, `LLMJudge`, `ToolCorrectness` | Later | Build cases from captured situation packets. Use `max_concurrency=1` for anything that touches the live game. |
| Dashboard | `bus.py` + SSE | AG-UI, Vercel AI, `to_web` | Skip | These are chat protocols. The dashboard is a passive monitor with replay by sequence number. |

## 5. Target architecture

```
runner thread ─┐                      ┌─ LLMService thread (one asyncio loop) ────────────────┐
improve thread ├── LLM.run(coro) ───► │ Agent.run(...) per role                               │
watchdog thread┘   (blocks caller)    │   ├─ RetryWithoutThinking(ConcurrencyLimitedModel(4, │
                                      │   │      OpenAIChatModel(VLLMProvider(AsyncOpenAI))))│
                                      │   ├─ capabilities: StepBudget, BusEvents, Interrupts,│
                                      │   │      ProcessHistory(history_guard)               │
                                      │   └─ toolsets: RegistryToolset(role filter)          │
                                      │         └─ sync tool bodies ─► thread pool ─► Bridge │
                                      └──────────────────────────────────────────────────────┘
dashboard thread (uvicorn) ◄── bus.py ◄── BusEvents hooks
watcher pool (4 threads) ── Bridge  (no change)
```

### 5.1 Module changes

| Module | Change |
|---|---|
| `llm.py` | Rewrite. Model factory, `LLMService` (loop thread, `run`, `close`), `RetryWithoutThinking`, HTTP capture hook. The `LLM` name can stay as the service class. |
| `agents.py` | New. `Deps`, output types (`TurnEnd`, `EpisodeEnd`, `WatchdogEnd`, `ManagerPlan`), one factory that builds each role's `Agent`. |
| `toolset.py` | New. `RegistryToolset`. |
| `capabilities.py` | New. `StepBudget`, `BusEvents`, `Interrupts`, `history_guard`. |
| `loop.py` | `think()` keeps its signature. Its body builds the run and calls the service. The situation packet and steward code do not change. |
| `registry.py` | Split `execute` so the adapter can raise `ToolFailed`. `coerce_param`, `remap_params`, `to_text` and the `@tool` decorator do not change. |
| `runner.py` | `play_step_parallel` and `manager_plan` move to the service. The `threading.Semaphore` goes away. |
| `watchdog.py`, `tools/watchdog.py` | `run_pass` uses the watchdog agent. `end_watchdog` becomes the output function. The gates do not change. |
| `export_sft.py` | Read the new capture record. Keep the output format. |
| `context.py` | `Context` stays. `Deps` holds a reference to it. |

### 5.2 Sketches

The model factory. Use `VLLMProvider` also for llama.cpp, LM Studio or a LiteLLM proxy. The Qwen profile then applies. `OpenAIProvider` and `LiteLLMProvider` give `Qwen/Qwen3-32B` the OpenAI profile.

```python
def build_model(cfg, capture) -> Model:
    client = AsyncOpenAI(
        base_url=cfg["base_url"], api_key=cfg["api_key"], timeout=cfg["timeout_s"], max_retries=0,
        http_client=httpx2.AsyncClient(event_hooks={"response": [capture.on_response]}),
    )
    chat = OpenAIChatModel(
        cfg["model"],
        provider=VLLMProvider(openai_client=client),
        profile=OpenAIModelProfile(
            openai_chat_send_back_thinking_parts=False,
            openai_chat_supports_max_completion_tokens=False,
            openai_supports_strict_tool_definition=False,
            context_window=cfg["context_window"],
        ),
        settings=ModelSettings(max_tokens=cfg["max_tokens"], temperature=0.6, parallel_tool_calls=False),
    )
    return RetryWithoutThinking(ConcurrencyLimitedModel(chat, limiter=cfg["max_streams"]))
```

The tool adapter. The validator accepts any JSON object. A top-level string (a double-encoded payload) then gives a retry prompt, not a crash. The rimagent dispatch does the coercion and the alias remap, as it does today.

```python
ANY_OBJECT = SchemaValidator(core_schema.dict_schema(core_schema.str_schema(), core_schema.any_schema()))


class RegistryToolset(AbstractToolset[Deps]):
    @property
    def id(self) -> str:
        return "rimagent_registry"

    async def get_tools(self, ctx):
        tools = ctx.deps.context.registry.visible(ctx.deps.groups, ctx.deps.allow)
        return {t.name: ToolsetTool(
                    toolset=self,
                    tool_def=ToolDefinition(name=t.name, parameters_json_schema=t.schema,
                                            description=t.description[:1024], sequential=t.name.startswith("rw_ui_")),
                    max_retries=3, args_validator=ANY_OBJECT)
                for t in tools}

    async def call_tool(self, name, tool_args, ctx, tool):
        result, ok = await anyio.to_thread.run_sync(ctx.deps.context.registry.execute, ctx.deps.context, name, tool_args)
        if not ok:
            raise ToolFailed(to_text(result))
        return as_tool_return(result)
```

The think step. `think()` keeps the old return type.

```python
def think(ctx, user_message, situation_hint="", *, max_calls=None, tool_groups=None, thinking=None,
          trigger="scheduled", tool_allow=None, system=None, end_tools=("end_turn", "end_episode")) -> StepResult:
    deps = Deps(context=ctx, groups=tool_groups, allow=tool_allow, max_calls=max_calls or ..., trigger=trigger)
    agent = agents.for_end_tools(end_tools)
    coro = agent.run(user_message, deps=deps, instructions=system or build_system(ctx, situation_hint or user_message[:2000]),
                     model_settings=agents.thinking_settings(thinking), usage_limits=deps.hard_limits())
    return agents.step_result(ctx.llm.run(coro), deps)
```

## 6. Phases

Each phase ends with green tests (`cd agent && uv run pytest -q`) and one commit. Do not start a phase before the previous one meets its exit criteria.

### Phase 0: spike and pin (size S)

Goal: prove the risky assumptions against the real vLLM server before any change to `agent/rimagent`.

1. Make a branch.
2. Add `pydantic-ai-slim[openai]==2.47.0` to `agent/pyproject.toml`. Pin the exact version.
3. Write `agent/scripts/spike_pydantic_ai.py`. Do not put it in the package.
4. With the spike, check these items and record each answer in section 10 of this plan:
   1. `tool_choice='required'` with Qwen3 thinking on and the hermes parser. Does vLLM return a valid tool call?
   2. The wire request: `chat_template_kwargs` present, `max_tokens` (not `max_completion_tokens`), no `strict`, no `reasoning_effort`, `stream` absent or false.
   3. `reasoning_content` becomes a `ThinkingPart`. It is not sent back on the next turn.
   4. Four concurrent `agent.run` calls on one loop with `ConcurrencyLimitedModel(4)`. No "bound to a different event loop" error.
   5. `ctx.enqueue(..., priority='asap')` from a hook after a tool batch. The text reaches the next model request.
   6. `end_turn` as an output function, with `rw_ui_*` calls in the same response. The function tools run first.
   7. The vLLM `max_model_len` value. Put it in `config.yaml` as `llm.context_window`.
5. Set `PYDANTIC_AI_NO_BANNER=1` for the spike and for `rimagent play`.

Exit criteria: every item has an answer. Each failed item has a fallback in this plan (see section 9).

### Phase 1: model layer (size M)

Goal: the new model layer runs in production for the low-risk calls. The think loop still uses the old client.

1. In `llm.py`, add `build_model`, `RetryWithoutThinking` and `LLMService`.
2. Add the HTTP capture hook. Write the same record fields as `LLM._capture`: `t`, `model`, `meta`, `messages`, `tools_ref`, `reply` (`content`, `reasoning`, `tool_calls`), `usage`, `elapsed`. Keep `_tools_ref` deduplication.
3. Set the capture `meta` in a `ContextVar` from a `wrap_model_request` hook. Fill it from `ctx.deps`.
4. Move `cli llm`, `seed.distill_skills` and `runner.manager_plan` to the service. The manager uses `Agent(output_type=ManagerPlan)` with thinking off, `max_tokens=900` and `temperature=0.3`.
5. Tests:
   1. The capture record from a stub HTTP server matches the old record shape.
   2. `RetryWithoutThinking` retries once on an empty reply and once on `ModelAPIError`, and it sends `enable_thinking: false` on the retry.
   3. The manager returns an empty plan when the model fails.

Exit criteria: `export_sft` reads captures from both the old and the new code. A live run shows manager plans on the dashboard.

### Phase 2: tool adapter (size M)

Goal: every registry tool is callable through Pydantic AI, with the same behavior.

1. Add `Registry.visible(groups, allow)`. Move the filter logic out of `Registry.specs`. `specs` calls `visible`.
2. Add `RegistryToolset` in `toolset.py`.
3. Return `ToolReturn` with `BinaryContent` when a result has `_image_png_b64`.
4. Mark `rw_ui_*` tools `sequential=True` in their `ToolDefinition`. `parallel_tool_calls=False` in the model settings is the main control. This flag is a second barrier.
5. Tests with `FunctionModel`:
   1. JSON-string arguments (`"[97, 98]"`, `"true"`, `"80"`) reach the tool as values.
   2. A double-encoded argument payload does not crash the run.
   3. An alias (`content` for `text`) still maps.
   4. A bridge error becomes a failed tool result, and the step continues.
   5. An unknown tool name gives a retry prompt, and the step continues.
   6. The watchdog role sees exactly the `_WATCHDOG_TOOLS` names. A play role never sees a `watchdog` group tool.
   7. A brain tool written during a step is callable in the next request.

Exit criteria: all tests pass. No change to `brain/tools/*.py` was necessary.

### Phase 3: think step on `Agent`, behind a flag (size L)

Goal: `think()` runs on Pydantic AI. The old loop stays available for comparison.

1. Add `llm.engine: legacy | pydantic_ai` to `config.yaml`. The default stays `legacy` in this phase.
2. Add `agents.py`: `Deps`, output types, the agent factory. Set `end_strategy='graceful'` and `retries={'tools': 3, 'output': 2}` explicitly.
3. Add `capabilities.py`:
   1. `StepBudget`: count every executed tool call in `deps`, as the old loop does. At the budget, hide all function tools in `prepare_tools` and enqueue the old text: "You have used N tool calls, the limit for this step. Call end_turn now to finish."
   2. `BusEvents`: emit `think_start`, `reasoning`, `assistant`, `tool_call`, `tool_result` and `think_end` with the same data fields as today. Emit a failed `tool_result` for every `ToolFailed`, validation error and unknown-tool retry. `watchdog.recent_errors` needs the call arguments and the `think_start` context.
   3. `Interrupts`: after each tool batch, call `deps.context.interrupt_check` and drain the operator inbox. Deliver the old text blocks with `ctx.enqueue(..., priority='asap')`.
   4. `history_guard`: a `ProcessHistory` function with the old 160k/120k-char rule.
4. Map the run outcome to `StepResult`:
   1. An output function result: `ended_by_tool=True`, notes from the function.
   2. `UnexpectedModelBehavior`, `UsageLimitExceeded`, `ModelAPIError`: `notes="LLM error: ..."`, emit an `error` event, keep the partial transcript from `capture_run_messages()`.
5. Coerce the arguments of the output functions inside their bodies (`wake_on`, `fixes`, `skipped` can arrive as JSON strings). Tool hooks do not run for output tools.
6. Tests:
   1. Replace `ScriptedLLM` in `test_watchdog.py` with `FunctionModel`. Keep every assertion.
   2. A text-only reply gets a retry prompt, and the step then ends with `end_turn`.
   3. The budget hides the tools at the limit, and the step ends cleanly.
   4. The bus event sequence for a scripted step equals a recorded sequence from the legacy engine.
   5. No request in any test uses streaming.
7. Run live A/B: one episode per engine on the same seed. Compare the tool-error rate, `end_turn` rate, tool calls per step, tokens per step, and seconds per step.

Exit criteria: the A/B numbers of the new engine are equal to or better than legacy. The dashboard and the watchdog tab show the same event types.

### Phase 4: parallel mode and cancellation (size M)

Goal: the fan-out runs on the loop service.

1. Rewrite `play_step_parallel`: `asyncio.gather(*role_runs, return_exceptions=True)` inside `anyio.fail_after(900)`, submitted once through the service.
2. Give each role run its own `Context.fork(role)`, as today.
3. Give every run a `CancellationToken`. `Controls.kill` and `Runner.stop` cancel all active tokens.
4. Remove `threading.Semaphore` from `llm.py`.
5. Tests: one role raises, and the other three still return notes. A cancelled run ends the step without a traceback in the runner.

Exit criteria: a live parallel episode runs for one in-game day with no event-loop errors.

### Phase 5: cut over and clean up (size S to M)

1. Set `llm.engine: pydantic_ai` as the default. Run one full episode.
2. Remove the legacy loop, `LLMReply`, `assistant_message` and the flag.
3. Update `AGENTS.md`, `README.md` and `docs/PAPER.md` appendix A. Also fix a present drift: `AGENTS.md` says the watchdog has two roots, but `watchdog.ALLOWED_ROOTS` has three (`mod-steward/Source` too), and `AGENTS.md` does not list `watchdog_verify_mod_steward`.
4. Remove the direct `openai>=1.50` lower bound. Set `openai>=3.8`.

Exit criteria: no import of the legacy code remains. All tests pass.

### Phase 6: optional Harness pieces (each size S)

Adopt each item alone. Measure it on one episode before the next item. Pin `pydantic-ai-harness==<exact version>` when the first item goes in. Read the release notes on each upgrade.

| Item | Replaces or adds | Condition to adopt |
|---|---|---|
| `ToolOutputLimits` with `Spill` + `read_tool_result` | Lossless large results in place of cut results | The `read_tool_result` cap (50k chars, 1k lines, not configurable) fits the Qwen context. Use `serializer=indented_json`. |
| `ClearToolResults(context_window=...)` | `history_guard` | Always pass `context_window`. Without it, the default is 200k tokens. |
| `FileSystem` for the watchdog (`read_file`, `edit_file`, `list_directory`, `find_files`, `search_files`) | `repo_read`, `repo_list`, `repo_grep`; `edit_file` in place of whole-file `repo_patch` | Keep `safe_path` as an extra check in a `before_tool_execute` hook: `FileSystem` allows `..` inside the root and cross-root symlinks. Mark roots unverified in the same hook. Do not use `FileChangeRequestEvent`: a listener switches requests to streaming. |
| `SpendLimits` token counters per episode and per day | Token counts on the dashboard | Use `tokens=` budgets. Local models have no price. |
| `StepPersistence(SqliteStepStore, max_snapshots_per_run=N)` | Structured per-step trajectories with run lineage | Only if the SFT or evaluation work needs it. It does not replace the HTTP capture. |
| `CodeMode` for play roles | A sandboxed alternative to `run_python` | Set `max_tool_calls` to the step budget. Nested calls are counted after the fact. |
| `TrajectoryJudge(every=3..5)` | Mid-step steering against tool-error loops | A judge failure ends the run. Use a `FallbackModel` in the judge. |

Do not adopt: `Coder`, `Shell` (unrestricted shell for the watchdog), `Memory`, `Skills`, `SubAgents`, `DynamicWorkflow`, `Planning`, `AskUser`, `Advisor` (local fallback only on vLLM), `PromptInjectionDefender`, `ManagedPrompt` (needs Logfire), and the cloud integrations.

### Phase 7: optional evaluation and tracing (size M)

1. Build a `pydantic_evals` dataset from captured situation packets. Replace the bridge toolset with a recorded or stub toolset.
2. Use `ToolCorrectness`, `ArgumentCorrectness`, `MaxToolCalls` and a local `LLMJudge`. Set `set_default_judge_model(...)` to a local model. The default judge is a hosted OpenAI model.
3. Let the improvement pass and the watchdog record the eval score before and after their changes.
4. Turn on `Instrumentation` with a local OpenTelemetry exporter. Pin the instrumentation `version=5`. The span-based evaluators need it.

## 7. Test plan

| Level | What | Tool |
|---|---|---|
| Unit | Coercion, alias remap, truncation, role filter, budget, output-function argument coercion, retry wrapper | `FunctionModel`, `TestModel(call_tools=[...])` |
| Contract | Bus event sequence and fields; SFT capture record; `recent_errors` stitching | recorded fixtures from the legacy engine |
| Safety | Watchdog tool list is exact; commit refused without verify; play roles never see `watchdog` tools | existing `test_watchdog.py` assertions on `FunctionModel` |
| Wire | No streaming; `extra_body` present; no `strict`; `max_tokens` field | stub HTTP server + capture hook |
| Live | A/B episode per engine on one seed | dashboard + `scores.jsonl` |

Test rules:

- Set `ALLOW_MODEL_REQUESTS = False` in `conftest.py`.
- Pass the model explicitly in code that runs in another thread. `Agent.override` and `capture_run_messages` use `ContextVar`s. They do not reach new threads.
- `TestModel()` calls every tool by default. Restrict `call_tools` when bridge tools are registered.

## 8. Dependencies

| Package | Pin | Phase |
|---|---|---|
| `pydantic-ai-slim[openai]` | `==2.47.0` | 0 |
| `openai` | `>=3.8` (lock has 3.14.1) | 5 |
| `httpx2` | transitive through Pydantic AI | 1 |
| `httpx` | keep `0.28.x` for the sync `Bridge` client | none |
| `pydantic-ai-harness` | exact pin | 6, only if an item is adopted |
| `pydantic-ai-slim[evals]` | same as core | 7 |

Do not install the full `pydantic-ai` package. It adds Anthropic, Google, MCP, CLI and web dependencies.

## 9. Risks

| Id | Risk | Mitigation |
|---|---|---|
| R1 | vLLM rejects or breaks `tool_choice='required'` with Qwen3 thinking. | Phase 0 item 4.1. Fallback: `openai_supports_tool_choice_required=False`. The output retry prompt then acts as the nudge. |
| R2 | A shared async client across threads fails. | One loop service for all model calls. Verified failure and verified fix. |
| R3 | The retry budget runs out and the step ends with `UnexpectedModelBehavior`. | `retries={'tools': 3, 'output': 2}`. Catch it at the step boundary, as the old "LLM error" path does. |
| R4 | A later change adds an event listener and switches requests to streaming. | A wire test asserts `stream` is absent or false. |
| R5 | The prompt or the wire request changes without notice. | Compare captures of one recorded step from both engines before the cut-over. Expected changes: `content: null` on tool-only assistant turns, merged leading system messages, retry prompt text. |
| R6 | A timed-out sync tool keeps running and the game action still happens. | Keep deadlines in the bridge HTTP client. Do not rely on `tool_timeout`. |
| R7 | Library churn. | Exact pins. Harness only in Phase 6, one item at a time. |
| R8 | `end_strategy='graceful'` runs tools that come after `end_turn` in one response. Today they are skipped. | Accept this. It is closer to the intent of the model than `'early'`, which skips all of them. Record it in the release notes. |
| R9 | `SFT` data shape changes. | The capture stays wire-exact. The changes in R5 are real model inputs, so the data stays correct. |

## 10. Open questions

1. Phase 0 answers (fill in after the spike): 4.1 ___, 4.2 ___, 4.3 ___, 4.4 ___, 4.5 ___, 4.6 ___, 4.7 ___.
2. How long must the `llm.engine` flag stay? Proposal: one episode after the A/B result.
3. Must each step also store its full `ModelMessage` history (`ModelMessagesTypeAdapter`) next to the wire capture? It costs disk space. It gives thinking, retry prompts and run ids in one typed record.
4. Will the project serve a vision model? The `look` tool sends images, and Qwen3-32B cannot read them.
