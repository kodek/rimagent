"""The three agents: the director plays, the improver and the reflector edit the brain. Same model, same brain."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.models import Model
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai_harness import (
    ClearToolResults,
    CodeMode,
    ReportContextUsage,
    StepPersistence,
    SummarizingCompaction,
    TieredCompaction,
    ToolOutputLimits,
    WarnNearLimits,
)
from pydantic_ai_harness.step_persistence import SqliteStepStore
from pydantic_ai_harness.tool_output_limits import Band, LocalFileStore, Spill, Truncate, indented_json

from .brain import Brain
from .capabilities.step import Interrupts, StepBudget
from .config import Settings
from .deps import Deps
from .history import BrainTools
from .tools.bridge import BridgeToolset
from .tools.code import CODE_MODE, sandbox
from .tools.turn import PASS_OUTPUT, PLAY_OUTPUT, EpisodeEnd, Finished, TurnEnd, operator
from .tools.vision import vision
from .watchers import WatcherTools, Watchers

DIRECTOR = """You are rimagent. You run a RimWorld colony by yourself through tools, and you keep improving your own brain:
your doctrine (AGENTS.md), skills, watchers, capabilities and memory. Nobody else will help.

Each step starts with a situation report: what woke you, what changed, the colony state. Act on the most urgent thing
with tools, keep the colony notebook current, then call end_turn with a wake plan. You keep this conversation for the
whole game, so you remember earlier steps; old tool results are cleared or summarized as it grows, so write what you
must not lose into the notebook.

- rw_* tools are the game (RimBridge). Read before you act on exact positions.
- look shows the map as an image with a coordinate grid and numbered marks on buildings.
- run_code runs Python in a sandbox where rpc(method, params) calls any RimBridge method: batch many reads and compute.
  The last expression is the result; return data, do not json.dumps it.
- load_capability loads a skill from the catalog. Load the skill for a situation before you act on it.
- A tool result that is too long is stored; page through it with read_tool_result.
- reply_to_operator answers the human operator. Answer each operator message first. If it is advice on how to play,
  write it into the relevant skill.
Be terse in visible text. Do the work with tool calls."""

IMPROVER = """You are rimagent's improvement pass. The game keeps running and another stream plays it; you only read the game.
Turn what the recent steps did by hand into automation and knowledge:
- a reaction repeated by hand becomes a watcher (dry-run it with test_watcher);
- a multi-call check repeated at every step becomes an authored capability;
- a strategy that worked or failed tightens the relevant skill, with concrete numbers;
- a durable lesson goes into the journal.
Change the smallest set of files that makes the next steps better. Finish with finish(notes)."""

REFLECTOR = """You are rimagent's episode reflection. This game is over. Make the next game go better:
1. Name the 2-4 decisions or omissions that mattered most, with evidence from the timeline.
2. Edit or create skills so the same situation goes better next time (triggers, steps, numbers).
3. Write or fix a watcher for a reaction that came too late.
4. Write one journal entry with durable lessons, not colony details.
5. Change AGENTS.md only for a rule that applies to every step.
Finish with finish(notes)."""


@dataclass
class Agents:
    director: Agent[Deps, TurnEnd | EpisodeEnd]
    improver: Agent[Deps, Finished]
    reflector: Agent[Deps, Finished]
    steps: SqliteStepStore


def _common(settings: Settings, brain: Brain, watchers: Watchers, history: BrainTools, budget: int) -> list[AbstractCapability[Deps]]:
    overflow = LocalFileStore(settings.runs / "overflow", cleanup_after=timedelta(days=2))
    return [
        StepBudget(budget),
        *brain.capabilities(),
        WatcherTools(watchers),
        history,
        CodeMode(tools=CODE_MODE),
        ToolOutputLimits(bands=[Band(over=10_000, action=Spill(then=Truncate()))], store=overflow, serializer=indented_json),
        WarnNearLimits(max_iterations=budget),
    ]


def build_agents(model: Model, settings: Settings, brain: Brain, watchers: Watchers, history: BrainTools) -> Agents:
    budget = settings.play.max_requests
    toolsets: list[AbstractToolset[Deps]] = [BridgeToolset().prefixed("rw"), sandbox]
    steps = SqliteStepStore(database=settings.runs / "steps.sqlite", max_snapshots_per_run=4)
    at = settings.context.compact_at_tokens
    compaction = TieredCompaction(
        tiers=[
            ClearToolResults(max_tokens=at, keep_pairs=settings.context.keep_tool_pairs, exclude_tools=frozenset({"load_capability"})),
            SummarizingCompaction(max_tokens=at, keep_messages=settings.context.keep_messages),
        ],
        target_tokens=at,
    )
    director = Agent(
        model,
        name="director",
        deps_type=Deps,
        output_type=PLAY_OUTPUT,
        instructions=[DIRECTOR, brain.guides()],
        retries={"tools": 3, "output": 3},
        end_strategy="graceful",
        toolsets=[*toolsets, operator, vision],
        capabilities=[
            *_common(settings, brain, watchers, history, budget),
            Interrupts(),
            compaction,
            ReportContextUsage(context_window=settings.llm.context_window),
            StepPersistence(store=steps, agent_name="director"),
        ],
    )

    def brain_pass(name: str, instructions: str) -> Agent[Deps, Finished]:
        return Agent(
            model,
            name=name,
            deps_type=Deps,
            output_type=PASS_OUTPUT,
            instructions=[instructions, brain.guides()],
            retries={"tools": 3, "output": 3},
            end_strategy="graceful",
            toolsets=toolsets,
            capabilities=_common(settings, brain, watchers, history, budget),
        )

    return Agents(director=director, improver=brain_pass("improver", IMPROVER), reflector=brain_pass("reflector", REFLECTOR), steps=steps)
