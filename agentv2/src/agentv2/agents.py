"""The three agents: the director plays, the improver and the reflector edit the brain. Same model, same brain."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import is_multi_modal_content
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
from pydantic_ai_harness.conversation_search import ConversationSearch, SnapshotHistorySource
from pydantic_ai_harness.repair_tool_arguments import RepairToolArguments
from pydantic_ai_harness.step_persistence import SqliteStepStore
from pydantic_ai_harness.tool_output_limits import Band, LocalFileStore, Spill, Truncate, indented_json

from .brain import Brain
from .capabilities.access import method_access
from .capabilities.arguments import CoerceArguments
from .capabilities.sandbox_calls import SandboxCalls, outside_sandbox
from .capabilities.speed import TrackSpeed
from .capabilities.step import StepBudget
from .capabilities.telemetry import telemetry
from .config import Settings
from .deps import Deps, DirectorDeps
from .history import BrainTools
from .roles import DIRECTOR, IMPROVER, REFLECTOR, Role
from .tools.bridge import BridgeToolset
from .tools.tracked import TrackedValues
from .tools.turn import PASS_OUTPUT, PLAY_OUTPUT, EpisodeEnd, Finished, TurnEnd, operator
from .tools.vision import vision
from .watchers.tools import WatcherTools


@dataclass
class Agents:
    director: Agent[DirectorDeps, TurnEnd | EpisodeEnd]
    improver: Agent[Deps, Finished]
    reflector: Agent[Deps, Finished]


def _measured_text(value: Any) -> str:
    """A run_code result can hold an image next to data; the image is not text for the size limit."""
    if isinstance(value, list):
        value = [f"<{item.kind}>" if is_multi_modal_content(item) else item for item in value]
    return indented_json(value)


def build_agents(model: Model, settings: Settings, brain: Brain, watcher_tools: WatcherTools, history: BrainTools,
                 steps: SqliteStepStore) -> Agents:
    budget = settings.play.max_requests
    toolsets: list[AbstractToolset[Deps]] = [BridgeToolset().prefixed("rw")]
    overflow = LocalFileStore(settings.runs / "overflow", cleanup_after=timedelta(days=2))

    def common() -> list[AbstractCapability[Deps]]:
        return [
            StepBudget(budget),
            RepairToolArguments(),
            CoerceArguments(),
            method_access(),
            *brain.capabilities(),
            watcher_tools,
            history,
            TrackedValues(),
            CodeMode(max_retries=budget),
            SandboxCalls(),
            telemetry(),
            ToolOutputLimits(bands=[Band(over=10_000, action=Spill(then=Truncate()))], store=overflow, serializer=_measured_text,
                             tool_filter=outside_sandbox),
            WarnNearLimits(max_iterations=budget),
        ]

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
        name=DIRECTOR.name,
        deps_type=DirectorDeps,
        output_type=PLAY_OUTPUT,
        instructions=[DIRECTOR.instructions, brain.guides()],
        retries={"tools": 3, "output": 3},
        end_strategy="graceful",
        toolsets=[*toolsets, operator, vision],
        capabilities=[
            *common(),
            TrackSpeed(),
            compaction,
            ReportContextUsage(context_window=settings.llm.context_window),
            StepPersistence(store=steps, agent_name=DIRECTOR.name),
        ],
    )

    def brain_pass(role: Role) -> Agent[Deps, Finished]:
        return Agent(
            model,
            name=role.name,
            deps_type=Deps,
            output_type=PASS_OUTPUT,
            instructions=[role.instructions, brain.guides()],
            retries={"tools": 3, "output": 3},
            end_strategy="graceful",
            toolsets=toolsets,
            capabilities=[*common(), ConversationSearch(SnapshotHistorySource(steps), scope="conversation")],
        )

    return Agents(director=director, improver=brain_pass(IMPROVER), reflector=brain_pass(REFLECTOR))
