"""The composition root: builds every part of a running agent once, for the CLI and the tests."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from pydantic_ai.models import Model
from pydantic_ai_harness.step_persistence import SqliteStepStore

from .agents import Agents, build_agents
from .brain import Brain, BrainLayout
from .bridge import Bridge, GameStatus
from .bus import Bus
from .config import Settings
from .controls import Controls
from .dashboard.brain_view import BrainView
from .director import DirectorSession, urgent_message
from .episode import EpisodeStore
from .events import Log
from .flags import RuntimeFlags
from .game import GameSwitches
from .history import BrainGit, BrainTools, Scores
from .passes import BrainPasses
from .poller import Inbox, LedgerPoller
from .runner import Runner
from .wake import WakePolicy
from .watchers import Watchers
from .watchers.tools import WatcherTools


@dataclass
class Runtime:
    settings: Settings
    bus: Bus
    bridge: Bridge
    brain: Brain
    watchers: Watchers
    agents: Agents
    director: DirectorSession
    runner: Runner
    controls: Controls
    brain_view: BrainView


@asynccontextmanager
async def open_runtime(settings: Settings, bus: Bus, bridge: Bridge, model: Model) -> AsyncIterator[Runtime]:
    layout = BrainLayout(settings.brain)
    brain = Brain(layout, settings.knowledge_dir)
    scores, git = Scores(layout.scores), BrainGit(layout.root)
    steps = SqliteStepStore(database=settings.runs / "steps.sqlite", max_snapshots_per_run=4)
    flags = RuntimeFlags(danger_think_speed=settings.play.danger_think_speed, steward=settings.steward.enabled,
                         orders_off=set(settings.steward.orders_off))
    inbox = Inbox()
    async with Watchers(layout.watchers_dir, bridge, bus, settings.watchers.timeout_s) as watchers:
        agents = build_agents(model, settings, brain, WatcherTools(watchers), BrainTools(scores, git, layout), steps)
        director = DirectorSession(agents.director, steps, brain, settings.play.max_requests)
        passes = BrainPasses(agents.improver, agents.reflector, brain, git, scores, bus, director, settings.play.max_requests)
        game = GameSwitches(bridge, bus, settings.steward, flags)

        async def on_urgent(items: list[str]) -> None:
            if director.interrupt(urgent_message(items)):
                await game.set_speed(flags.danger_think_speed)

        def on_menu() -> None:
            if director.active is not None:
                bus.emit(Log(text="the game is at the main menu: the running step stops"))
                director.cancel()

        async def on_day(st: GameStatus) -> None:
            await runner.day_rollover(st)

        poller = LedgerPoller(bridge, bus, watchers, inbox, settings, on_urgent, on_menu, on_day)
        runner = Runner(settings, bus, bridge, flags, inbox, EpisodeStore(settings.runs / "episode.json"), poller, WakePolicy(settings.play),
                        game, director, passes, brain, watchers, scores)
        controls = Controls(flags, inbox, director, game, brain.operator, bus, lambda: runner.episode)
        brain_view = BrainView(brain, watchers, git, scores, lambda: runner.episode)
        yield Runtime(settings, bus, bridge, brain, watchers, agents, director, runner, controls, brain_view)
