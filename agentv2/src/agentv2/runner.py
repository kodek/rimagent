"""The episode runner: starts or resumes a game, wakes the director, starts the brain passes, and scores the episode.
One asyncio loop runs everything: the poller and the watchers, think steps, brain passes and the dashboard."""
from __future__ import annotations

import asyncio
import re
import shutil
import time
import traceback
from dataclasses import dataclass, field

from . import situation, world
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
    base_shown: bool = field(default=False, init=False)
    last_day: int = field(default=-1, init=False)
    improve_task: asyncio.Task[str] | None = field(default=None, init=False)
    start_new_game: bool = field(default=False, init=False)
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
        if self.start_new_game:
            self.start_new_game = False
            if saved := self.episodes.load():
                self.bus.emit(Log(text=f"episode {saved.number} is left without a score: a new game starts"))
            await self.new_game()
            return
        st = await self.bridge.status()
        if st.state == "loading":
            while (await self.bridge.status()).state == "loading":
                await asyncio.sleep(2)
            return
        if st.playing:
            if not self.episode.seed:
                saved = self.episodes.load()
                if saved and saved.ended and saved.seed == st.seed:
                    self.episode = Episode(number=saved.number)
                    await self.new_game()
                else:
                    await self.resume(st, saved)
            return
        episode = self.episode if self.episode.unfinished else self.episodes.load()
        if episode and episode.unfinished and episode.checkpoint and await self._has_save():
            await self.reload(episode)
        else:
            await self.new_game()

    def _next_episode_number(self) -> int:
        """After the scored episodes, the stored one (scored or abandoned) and every colony notebook in the brain."""
        saved = self.episodes.load()
        notebooks = [int(m[1]) for d in self.brain.layout.memory_dir.iterdir() if (m := re.match(r"episode-(\d+)-", d.name))]
        return max([int(r.get("episode") or 0) for r in self.scores.history(10_000)] + [saved.number if saved else 0] + notebooks) + 1

    def _reset(self) -> None:
        self.inbox.clear()
        self.wake.reset()
        self.base_shown = False
        self.poller.last_seq = 0
        self.poller.lost_contact = False

    async def resume(self, st: GameStatus, saved: Episode | None) -> None:
        seed = st.seed or "resumed"
        self._reset()
        self.flags.sandbox = st.god_mode
        if saved and saved.seed == seed:
            self.episode = saved.model_copy(update={"sandbox": st.god_mode})
        else:
            self.episode = Episode(number=self._next_episode_number(), seed=seed, start_day=st.day, sandbox=st.god_mode, last_improve_day=st.day)
        self.poller.last_seq, self.last_day = st.seq, st.day
        restored = len(await self.director.history(self.episode.colony))
        self.bus.emit(EpisodeStart(episode=self.episode.number, seed=seed, resumed=True, day=self.episode.start_day, restored_messages=restored))
        self.bus.emit(Status(episode=self.episode.number, seed=seed, deaths=self.episode.deaths, raids=self.episode.raids))
        await self.game.apply_steward()
        await self.save_game(st)
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
        shutil.rmtree(self.settings.scratch, ignore_errors=True)
        self.settings.scratch.mkdir(parents=True)
        self.episode = Episode(number=number, seed=seed, start_day=st.day, sandbox=self.flags.sandbox, last_improve_day=st.day)
        self.poller.last_seq, self.last_day = st.seq, st.day
        if self.flags.sandbox:
            await self.game.apply_sandbox(self.episode, True)
        await self.game.apply_steward()
        await self.game.queue_research()
        self.bus.emit(EpisodeStart(episode=number, seed=seed, sandbox=self.flags.sandbox))
        self.bus.emit(Status(deaths=0, raids=0))
        self.episodes.save(self.episode)
        await self.save_game(st)
        self.inbox.forced = Wake("new game started", False)

    async def reload(self, episode: Episode) -> None:
        """Continue an unfinished episode from its save, after a game crash or restart."""
        name = self.settings.play.save_name
        self.bus.emit(Status(phase="loading", episode=episode.number, seed=episode.seed))
        self.bus.emit(Log(text=f"loading {name} to continue episode {episode.number}"))
        try:
            await self.bridge.call("game.load", {"name": name})
            await asyncio.sleep(3)
            st = await self.bridge.wait_for("playing", 600)
        except BridgeError as e:
            self.bus.emit(Error(text=f"loading {name}: {e}"))
            episode.checkpoint = None
            self.episode = episode
            await self.end_episode("the game crashed and its save did not load")
            return
        self._reset()
        cp = episode.rewind(st)
        self.episode = episode
        self.poller.last_seq, self.last_day = st.seq, st.day
        self.flags.sandbox = episode.sandbox
        if episode.sandbox:
            await self.game.apply_sandbox(episode, True)
        await self.game.apply_steward()
        self.episodes.save(episode)
        self.bus.emit(EpisodeStart(episode=episode.number, seed=episode.seed, resumed=True, reloaded=name, day=st.day))
        self.bus.emit(Status(episode=episode.number, seed=episode.seed, deaths=episode.deaths, raids=episode.raids))
        self.inbox.forced = Wake(f"the game crashed and was loaded from its save of day {cp.day} {cp.hour}h: all that happened after "
                                 "that save is undone, so read the colony again before you act", False)

    async def save_game(self, st: GameStatus) -> None:
        if not self.settings.play.autosave:
            return
        try:
            await self.bridge.call("game.save", {"name": self.settings.play.save_name})
        except BridgeError as e:
            self.bus.emit(Error(text=f"save: {e}"))
            return
        self.episode.saved(st)
        self.episodes.save(self.episode)

    async def _has_save(self) -> bool:
        saves = await self.bridge.call("game.list_saves") or []
        return any(s.get("name") == self.settings.play.save_name for s in saves)

    async def recover(self) -> None:
        """Wait until RimBridge answers again; run `play.restart_command` while it stays silent."""
        play = self.settings.play
        self.bus.emit(Status(phase="loading"))
        silent_since = time.monotonic()
        while not self.flags.stop:
            health = await self.bridge.health()
            if health and health.get("mainThreadAlive"):
                try:
                    await self.load_catalog()
                    return
                except BridgeError as e:
                    self.bus.emit(Error(text=f"method catalog: {e}"))
            if play.restart_command and time.monotonic() - silent_since >= play.restart_after_s:
                await self.restart_game()
                silent_since = time.monotonic()
            await asyncio.sleep(3)

    async def restart_game(self) -> None:
        command = self.settings.play.restart_command
        self.bus.emit(Log(text=f"RimBridge did not answer for {self.settings.play.restart_after_s:.0f}s; restarting the game: {' '.join(command)}"))
        try:
            proc = await asyncio.create_subprocess_exec(*command, cwd=self.settings.root, stdout=asyncio.subprocess.PIPE,
                                                        stderr=asyncio.subprocess.STDOUT)
        except OSError as e:
            self.bus.emit(Error(text=f"restart command: {e}"))
            return
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), 120)
        except TimeoutError:
            proc.kill()
            self.bus.emit(Error(text="restart command: no exit after 120 s; killed"))
            return
        if proc.returncode:
            self.bus.emit(Error(text=f"restart command exited with {proc.returncode}: {out.decode(errors='replace')[-300:]}"))

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
                if self.poller.lost_contact and self.episode.checkpoint and await self._has_save():
                    self.bus.emit(Log(text="the game came back after a crash: the episode continues from its save"))
                    return
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

    async def day_rollover(self, st: GameStatus) -> None:
        """The poller calls it on every poll, also while the director thinks: a step can last several in-game days."""
        if st.day == self.last_day:
            return
        day = self.last_day = st.day
        self.episodes.save(self.episode)
        await self.save_game(st)
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
        episode, snap = self.episode, await situation.read(self.bridge)
        if snap.summary:
            await world.sample(self.bridge, episode.tracked, snap.summary)
        wakeup = situation.Wakeup(wake.trigger, events, alerts, list(self.inbox.operator), episode.view, episode.tracked,
                                  self.brain.problems() | self.watchers.errors(), episode.sandbox, show_base=not self.base_shown)
        report = situation.render(snap, wakeup)
        if snap.summary:
            episode.view, self.base_shown = snap.view, True
            self.episodes.save(episode)
        self.bus.emit(Status.model_validate(report.numbers))
        self.bus.emit(Situation(trigger=wake.trigger, changes=report.changes, day=report.day, hour=report.hour, chars=len(report.text)))
        deps = self.director_deps()
        deps.relevant_skills = self.brain.skills.matching(situation.wake_text(snap, wakeup))
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
        elif self.inbox.operator and not outcome.error:
            self.inbox.forced = Wake("operator message", True)
        try:
            tick = (await self.bridge.status()).tick
        except BridgeError:
            tick = self.poller.status.tick
        if outcome.error:
            self.wake.retry(tick, wake)
        else:
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
        assisted = st.assisted or episode.assisted or episode.sandbox
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
