"""The episode runner: starts or resumes a game, wakes the director, starts the brain passes, and scores the episode.
One asyncio loop runs everything: the poller and the watchers, think steps, brain passes and the dashboard."""
from __future__ import annotations

import asyncio
import time
import traceback
from dataclasses import dataclass, field

from . import situation
from .brain import Brain
from .bridge import Bridge, BridgeError, GameStatus
from .bus import Bus
from .catalog import Method, parse_catalog
from .config import Settings
from .deps import Deps, DirectorDeps
from .director import DirectorSession, StepOutcome
from .episode import Episode, EpisodeStore
from .events import EpisodeEnd, EpisodeStart, Error, Log, Situation, Status
from .flags import RuntimeFlags
from .game import GameSwitches
from .history import Scores, score
from .passes import BrainPasses
from .poller import Inbox, LedgerPoller
from .roles import DIRECTOR, IMPROVER, REFLECTOR, Role
from .wake import Wake, WakePolicy
from .watchers import Watchers


@dataclass
class Runner:
    settings: Settings
    bus: Bus
    bridge: Bridge
    flags: RuntimeFlags
    inbox: Inbox
    episodes: EpisodeStore
    poller: LedgerPoller
    wake: WakePolicy
    game: GameSwitches
    director: DirectorSession
    passes: BrainPasses
    brain: Brain
    watchers: Watchers
    scores: Scores
    episode: Episode = field(default_factory=Episode, init=False)
    catalog: list[Method] = field(default_factory=list, init=False)
    numbers: dict[str, float] = field(default_factory=dict, init=False)
    last_day: int = field(default=-1, init=False)
    improve_task: asyncio.Task[str] | None = field(default=None, init=False)
    _alerts_read: float = field(default=0.0, init=False)

    def deps(self, role: Role) -> Deps:
        return Deps(bridge=self.bridge, bus=self.bus, catalog=self.catalog, episode=self.episode, role=role)

    def director_deps(self) -> DirectorDeps:
        return DirectorDeps(bridge=self.bridge, bus=self.bus, catalog=self.catalog, episode=self.episode, role=DIRECTOR)

    # ------------------------------------------------------------------ lifecycle

    async def run(self) -> None:
        await self.prepare()
        poller = asyncio.create_task(self.poller.run(lambda: self.episode, lambda: self.flags.stop), name="poller")
        try:
            while not self.flags.stop:
                try:
                    await self.ensure_game()
                    await self.play_episode()
                except BridgeError as e:
                    self.bus.emit(Error(text=f"bridge: {e}"))
                    await self.recover()
                except Exception as e:  # noqa: BLE001 - the unattended runner reports and keeps playing
                    self.bus.emit(Error(text=f"runner: {e}\n{traceback.format_exc(limit=6)}"))
                    await asyncio.sleep(5)
        finally:
            poller.cancel()
            if self.improve_task:
                self.improve_task.cancel()
        self.bus.emit(Log(text="runner stopped"))

    async def prepare(self) -> None:
        self.bus.emit(Log(text=f"waiting for RimBridge at {self.bridge.url}"))
        await self.bridge.wait_alive()
        await self.load_catalog()

    async def load_catalog(self) -> None:
        self.catalog[:] = parse_catalog(await self.bridge.methods())
        self.bus.emit(Log(text=f"{len(self.catalog)} RimBridge methods as tools"))

    async def ensure_game(self) -> None:
        st = await self.bridge.status()
        if st.playing:
            if not self.episode.seed:
                saved = self.episodes.load()
                if saved and saved.ended and saved.seed == st.seed:
                    self.episode = Episode(number=saved.number)
                    await self.new_game()
                else:
                    await self.resume(st, saved)
            return
        if st.state == "loading":
            while (await self.bridge.status()).state == "loading":
                await asyncio.sleep(2)
            return
        await self.new_game()

    def _next_episode_number(self) -> int:
        return max([int(r.get("episode") or 0) for r in self.scores.history(10_000)] + [0]) + 1

    def _reset(self) -> None:
        self.inbox.clear()
        self.wake.reset()
        self.numbers = {}
        self.poller.last_seq = 0

    async def resume(self, st: GameStatus, saved: Episode | None) -> None:
        seed = st.seed or "resumed"
        self._reset()
        self.flags.sandbox = st.god_mode
        if saved and saved.seed == seed:
            self.episode = saved.model_copy(update={"sandbox": st.god_mode})
        else:
            self.episode = Episode(number=self._next_episode_number(), seed=seed, start_day=st.day, sandbox=st.god_mode)
        self.poller.last_seq, self.last_day = st.seq, st.day
        restored = await self.director.restore(self.episode.colony)
        self.bus.emit(EpisodeStart(episode=self.episode.number, seed=seed, resumed=True, day=self.episode.start_day, restored_messages=restored))
        self.bus.emit(Status(episode=self.episode.number, seed=seed, deaths=self.episode.deaths, raids=self.episode.raids))
        await self.game.apply_steward()
        self.inbox.forced = Wake("agent (re)started mid-game", False)

    async def new_game(self) -> None:
        play = self.settings.play
        number = max(self._next_episode_number(), self.episode.number + 1)
        seed = play.seeds[(number - 1) % len(play.seeds)]
        self.bus.emit(Status(phase="loading", episode=number, seed=seed))
        await self.bridge.call("game.new_game", {"seed": seed, "scenario": play.scenario, "storyteller": play.storyteller, "difficulty": play.difficulty})
        await asyncio.sleep(3)
        st = await self.bridge.wait_for("playing", 600)
        self._reset()
        self.episode = Episode(number=number, seed=seed, start_day=st.day, sandbox=self.flags.sandbox, last_improve_day=st.day)
        self.last_day = st.day
        self.director.reset()
        if self.flags.sandbox:
            await self.game.apply_sandbox(self.episode, True)
        await self.game.apply_steward()
        self.bus.emit(EpisodeStart(episode=number, seed=seed, sandbox=self.flags.sandbox))
        self.bus.emit(Status(deaths=0, raids=0))
        self.episodes.save(self.episode)
        self.inbox.forced = Wake("new game started", False)

    async def recover(self) -> None:
        self.bus.emit(Status(phase="loading"))
        for _ in range(40):
            if self.flags.stop or await self.bridge.health():
                break
            await asyncio.sleep(3)
        await self.bridge.wait_alive()
        await self.load_catalog()

    # ------------------------------------------------------------------ the episode

    async def play_episode(self) -> None:
        play = self.settings.play
        await self.bridge.call("game.speed", {"speed": play.speed})
        self.bus.emit(Status(phase="playing"))
        while not self.flags.stop:
            st = await self.bridge.status()
            if not st.playing:
                if st.state == "loading":
                    await asyncio.sleep(2)
                    continue
                await self.end_episode("the game left the play state")
                return
            if st.colonists == 0 and st.day > self.episode.start_day:
                await self.end_episode("all colonists dead")
                return
            if self.inbox.end:
                reason, self.inbox.end = self.inbox.end, None
                await self.end_episode(reason)
                return
            if st.day - self.episode.start_day >= play.max_days:
                await self.end_episode(f"reached max_days ({play.max_days})")
                return
            if st.day != self.last_day:
                await self.day_rollover(st.day)
            if self.flags.paused:
                await asyncio.sleep(1)
                continue
            wake = self.inbox.take_forced() or self.wake.check(st.tick, self.inbox.alerts, self.inbox.events, await self._game_alerts())
            if wake is None:
                await asyncio.sleep(0.5)
                continue
            outcome = await self.step(wake)
            if outcome.episode_end:
                await self.end_episode(outcome.episode_end)
                return

    async def day_rollover(self, day: int) -> None:
        self.last_day = day
        self.episodes.save(self.episode)
        if self.settings.play.autosave:
            try:
                await self.bridge.call("game.save", {"name": "agentv2-autosave"})
            except BridgeError as e:
                self.bus.emit(Error(text=f"autosave: {e}"))
        play, episode = self.settings.play, self.episode
        first = episode.last_improve_day == episode.start_day and day - episode.start_day >= play.first_improve_day
        due = first or day - episode.last_improve_day >= play.improve_every_days
        if due and not (self.improve_task and not self.improve_task.done()):
            episode.last_improve_day = day
            self.improve_task = asyncio.create_task(self.passes.improve(self.deps(IMPROVER), day), name="improve")
            self.improve_task.add_done_callback(self._report_failure)

    async def _game_alerts(self) -> list[dict] | None:
        if time.monotonic() - self._alerts_read < 5:
            return None
        self._alerts_read = time.monotonic()
        try:
            return await self.bridge.call("state.alerts") or []
        except BridgeError:
            return None

    async def step(self, wake: Wake) -> StepOutcome:
        events, alerts = self.inbox.take()
        wakeup = situation.Wakeup(wake.trigger, events, alerts, list(self.inbox.operator), self.numbers,
                                  self.brain.problems() | self.watchers.errors(), self.episode.sandbox)
        report = situation.render(await situation.read(self.bridge), wakeup)
        self.numbers = report.numbers
        self.bus.emit(Status.model_validate(report.numbers))
        self.bus.emit(Situation(trigger=wake.trigger, changes=report.changes, day=report.day, hour=report.hour, chars=len(report.text)))
        deps = self.director_deps()
        await self.game.set_speed(self.flags.danger_think_speed if wake.urgent else self.settings.play.think_speed)
        self.bus.emit(Status(phase="thinking"))
        try:
            outcome = await self.director.step(report.text, deps, wake)
        finally:
            chosen = deps.turn.model_speed
            await self.game.set_speed(self.settings.play.speed if chosen is None else max(1, chosen))
            self.bus.emit(Status(phase="playing", model_speed=chosen))
        if deps.turn.replies:
            self.inbox.operator.clear()
        elif self.inbox.operator:
            self.inbox.forced = Wake("operator message", True)
        try:
            tick = (await self.bridge.status()).tick
        except BridgeError:
            tick = self.poller.status.tick
        self.wake.schedule(tick, outcome.end, urgent=wake.urgent, model_speed=chosen)
        self.bus.emit(Status(next_wake_tick=self.wake.next_tick))
        return outcome

    def _report_failure(self, task: asyncio.Task[str]) -> None:
        if not task.cancelled() and (error := task.exception()):
            self.bus.emit(Error(text=f"{task.get_name()}: {error!r}\n" + "".join(traceback.format_exception(error, limit=6))))

    async def end_episode(self, reason: str) -> None:
        self.bus.emit(Status(phase="reflecting"))
        await self.game.set_speed(0)
        if self.improve_task:
            await asyncio.wait({self.improve_task})
        episode = self.episode
        st, summary = self.poller.status, {}
        try:
            st = await self.bridge.status()
            summary = await self.bridge.call("state.summary")
        except BridgeError as e:
            self.bus.emit(Error(text=f"final read: {e}"))
        days = max(st.day, self.last_day) - episode.start_day
        colonists = int(summary.get("colonists", st.colonists) or 0)
        assisted = st.assisted or episode.sandbox
        total = score(days, colonists, episode.deaths, float(summary.get("wealth", 0) or 0), float(summary.get("mood_avg", 0) or 0),
                      int(summary.get("research_done", 0) or 0), episode.raids)
        self.bus.emit(Log(text=f"episode {episode.number} over: {reason}; days={days} colonists={colonists} deaths={episode.deaths} score={total}"))
        notes = await self.passes.reflect(self.deps(REFLECTOR), reason, days, total)
        sha = await self.passes.brain_sha()
        self.scores.record({"episode": episode.number, "seed": episode.seed, "days": days, "colonists": colonists, "deaths": episode.deaths,
                            "raids": episode.raids, "wealth": summary.get("wealth"), "mood": summary.get("mood_avg"), "research": summary.get("research_done"),
                            "score": total, "assisted": assisted, "brain_sha": sha, "ended": reason, "notes": notes[:500]})
        episode.ended = True
        self.episodes.save(episode)
        await self.passes.commit(f"episode {episode.number}: score")
        self.bus.emit(EpisodeEnd(episode=episode.number, score=total, reason=reason, assisted=assisted, brain_sha=sha, days=days))
        self.episode = Episode(number=episode.number)
        if not self.flags.stop:
            await self.new_game()
