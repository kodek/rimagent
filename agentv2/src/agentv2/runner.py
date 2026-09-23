"""The episode runner. One asyncio loop runs everything: the game poller and the watchers, think steps, brain passes,
and the dashboard. A game is one continuous conversation with the director, compacted as it grows and persisted, so an
agent restart continues where it stopped."""
from __future__ import annotations

import asyncio
import collections
import json
import time
import traceback
from dataclasses import dataclass
from typing import Any

from pydantic_ai import UsageLimits, capture_run_messages
from pydantic_ai.exceptions import AgentRunError, UserError
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_ai_harness.step_persistence import continue_run

from . import situation
from .agents import Agents, build_agents
from .brain import AUTHORED, Brain, BrainLayout
from .bridge import Bridge, BridgeError, GameStatus
from .bus import Bus
from .catalog import parse_catalog
from .config import Settings
from .deps import Deps, Episode, Turn
from .history import BrainGit, BrainTools, GitError, Scores, score
from .telemetry import Telemetry
from .tools.turn import EpisodeEnd, TurnEnd
from .watchers import Alert, Watchers

TICKS_PER_HOUR = 2500
TIMELINE_KINDS = {"day", "colonist_died", "colonist_downed", "incident", "hostile_group", "hostile_group_gone", "letter", "mental_break",
                  "research_finished", "building_lost", "colonist_joined", "colonist_left", "quest"}


@dataclass
class Wake:
    trigger: str
    urgent: bool


@dataclass
class StepOutcome:
    notes: str
    end: TurnEnd | None = None
    episode_end: str | None = None
    error: str | None = None


class Runner:
    def __init__(self, settings: Settings, bus: Bus, bridge: Bridge, model: Model) -> None:
        self.s = settings
        self.bus = bus
        self.bridge = bridge
        self.model = model
        self.brain = Brain(BrainLayout(settings.brain), settings.knowledge_dir)
        self.scores = Scores(self.brain.layout.scores)
        self.git = BrainGit(self.brain.layout.root)
        self.watchers = Watchers(self.brain.layout.watchers_dir, bridge, bus, settings.watchers.timeout_s)
        self.episode_file = settings.runs / "episode.json"
        self.catalog: list = []
        self.episode = Episode()
        self.deps: Deps | None = None
        self.history: list[ModelMessage] = []
        self.stop = False
        self.agent_paused = False
        self.sandbox = False
        self.steward = settings.steward.enabled
        self.force: str | None = None
        self.force_end: str | None = None
        self.thinking = False
        self.status = GameStatus()
        self.step_no = 0
        self.improve_task: asyncio.Task[None] | None = None
        self.agents: Agents
        self._status_emitted = 0.0
        self._watched = 0.0
        self._alerts_read = 0.0
        self._reset_episode_state()

    def _reset_episode_state(self) -> None:
        self.last_seq = 0
        self.pending_events: list[dict[str, Any]] = []
        self.pending_alerts: list[Alert] = []
        self.operator_queue: list[str] = []
        self.timeline: list[dict[str, Any]] = []
        self.step_notes: list[str] = []
        self.numbers: dict[str, float] = {}
        self.deaths = self.raids = 0
        self.next_wake_tick = 0
        self.last_step_end_tick = 0
        self.turn_wake_on: set[str] = set()
        self.seen_alerts: dict[str, int] = {}
        self.last_day = -1
        self.last_improve_day = 0
        self.improve_seq = self.bus.last_seq

    # ------------------------------------------------------------------ lifecycle

    async def run(self) -> None:
        async with self.watchers:
            await self.prepare()
            poller = asyncio.create_task(self.poll_forever(), name="poller")
            try:
                while not self.stop:
                    try:
                        await self.ensure_game()
                        await self.play_episode()
                    except BridgeError as e:
                        self.bus.emit("error", {"text": f"bridge: {e}"})
                        await self.recover()
                    except Exception as e:  # noqa: BLE001 - the unattended runner reports and keeps playing
                        self.bus.emit("error", {"text": f"runner: {e}\n{traceback.format_exc(limit=6)}"})
                        await asyncio.sleep(5)
            finally:
                poller.cancel()
                if self.improve_task:
                    self.improve_task.cancel()
        self.bus.emit("log", {"text": "runner stopped"})

    async def prepare(self) -> None:
        """Build the agents and read the method catalog. Call inside `async with runner.watchers`."""
        self.agents = build_agents(self.model, self.s, self.brain, self.watchers, BrainTools(self.scores, self.git, self.brain.layout))
        self.bus.emit("log", {"text": f"waiting for RimBridge at {self.bridge.url}"})
        await self.bridge.wait_alive()
        await self.load_catalog()

    async def load_catalog(self) -> None:
        self.catalog = parse_catalog(await self.bridge.methods())
        self.bus.emit("log", {"text": f"{len(self.catalog)} RimBridge methods as tools"})

    def _new_deps(self) -> None:
        self.deps = Deps(bridge=self.bridge, bus=self.bus, settings=self.s, catalog=self.catalog, episode=self.episode)

    async def ensure_game(self) -> None:
        st = await self.bridge.status()
        if st.playing:
            if not self.episode.seed:
                saved = json.loads(self.episode_file.read_text()) if self.episode_file.exists() else {}
                if saved.get("ended") and saved.get("seed") == st.seed:
                    self.episode = Episode(number=int(saved.get("episode", 0)))
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

    async def resume(self, st: GameStatus, saved: dict[str, Any]) -> None:
        seed = st.seed or "resumed"
        same = saved.get("seed") == seed
        self._reset_episode_state()
        self.sandbox = st.god_mode
        self.episode = Episode(number=int(saved.get("episode", 0)) if same else self._next_episode_number(), seed=seed,
                               start_day=int(saved.get("start_day", 0)) if same else st.day, sandbox=self.sandbox)
        if same:
            self.deaths, self.raids = int(saved.get("deaths", 0)), int(saved.get("raids", 0))
            self.last_improve_day = int(saved.get("last_improve_day", self.episode.start_day))
        self.last_seq, self.last_day = st.seq, st.day
        self._new_deps()
        self.history = await self.restore_conversation()
        self.bus.emit("episode_start", {"episode": self.episode.number, "seed": seed, "resumed": True, "day": self.episode.start_day,
                                        "restored_messages": len(self.history)})
        await self.apply_steward()
        self.force = "agent (re)started mid-game"

    async def restore_conversation(self) -> list[ModelMessage]:
        runs = await self.agents.steps.list_runs(conversation_id=self.episode.colony)
        return await continue_run(self.agents.steps, run_id=runs[-1].run_id) if runs else []

    async def new_game(self) -> None:
        play = self.s.play
        number = max(self._next_episode_number(), self.episode.number + 1)
        seed = play.seeds[(number - 1) % len(play.seeds)]
        self.bus.emit("status", {"phase": "loading", "episode": number, "seed": seed})
        await self.bridge.call("game.new_game", {"seed": seed, "scenario": play.scenario, "storyteller": play.storyteller, "difficulty": play.difficulty})
        await asyncio.sleep(3)
        st = await self.bridge.wait_for("playing", 600)
        self._reset_episode_state()
        self.episode = Episode(number=number, seed=seed, start_day=st.day, sandbox=self.sandbox)
        self.last_day = self.last_improve_day = self.episode.start_day
        self.history = []
        self._new_deps()
        if self.sandbox:
            await self.apply_sandbox(True)
        await self.apply_steward()
        self.bus.emit("episode_start", {"episode": number, "seed": seed, "sandbox": self.sandbox})
        self.save_episode()
        self.force = "new game started"

    def save_episode(self, ended: bool = False) -> None:
        self.episode_file.parent.mkdir(parents=True, exist_ok=True)
        self.episode_file.write_text(json.dumps({"episode": self.episode.number, "seed": self.episode.seed, "start_day": self.episode.start_day,
                                                 "deaths": self.deaths, "raids": self.raids, "last_improve_day": self.last_improve_day,
                                                 "ended": ended}))

    async def recover(self) -> None:
        self.bus.emit("status", {"phase": "loading"})
        for _ in range(40):
            if self.stop or await self.bridge.health():
                break
            await asyncio.sleep(3)
        await self.bridge.wait_alive()
        await self.load_catalog()

    # ------------------------------------------------------------------ polling (runs all the time, also while thinking)

    async def poll_forever(self) -> None:
        while not self.stop:
            try:
                await self.poll_once()
            except BridgeError:
                pass
            except Exception as e:  # noqa: BLE001 - the poller reports and keeps polling; the main loop owns recovery
                self.bus.emit("error", {"text": f"poller: {e}\n{traceback.format_exc(limit=6)}"})
            await asyncio.sleep(0.5)

    async def poll_once(self) -> None:
        st = await self.bridge.status()
        self.status = st
        if time.monotonic() - self._status_emitted >= 1.0:
            self._status_emitted = time.monotonic()
            self.bus.emit("status", {**st.model_dump(exclude_unset=True), "episode": self.episode.number, "seed": self.episode.seed, "deaths": self.deaths, "raids": self.raids,
                                     "phase": "thinking" if self.thinking else "playing", "next_wake_tick": self.next_wake_tick, "steward": self.steward})
        if not st.playing or not self.episode.seed:
            return
        data = await self.bridge.events(self.last_seq, 500)
        events = data.get("events") or []
        if events:
            self.last_seq = int(data.get("last_seq", self.last_seq))
            for e in events:
                self.bus.emit("ledger", e)
                self.deaths += e.get("kind") == "colonist_died"
                self.raids += e.get("kind") == "hostile_group"
            self.pending_events += events
            self.timeline += [e for e in events if e.get("kind") in TIMELINE_KINDS]
        alerts: list[Alert] = []
        if events or time.monotonic() - self._watched >= self.s.watchers.poll_s:
            self._watched = time.monotonic()
            alerts = await self.watchers.run_all(events, st.model_dump())
            self.pending_alerts += alerts
        if self.thinking and self.deps is not None:
            urgent = [f"{e.get('kind')}: {e.get('text', '')}" for e in events if e.get("kind") in self.s.play.critical_kinds]
            urgent += [f"watcher {a.watcher}: {a.text}" for a in alerts if a.wake]
            if urgent:
                self.deps.urgent.append("## URGENT, happened while you were working\n" + "\n".join(f"- {u}" for u in urgent)
                                        + "\nDeal with these first, then continue.")
                await self.set_speed(self.s.play.danger_think_speed)

    # ------------------------------------------------------------------ the episode

    async def play_episode(self) -> None:
        play = self.s.play
        await self.bridge.call("game.speed", {"speed": play.speed})
        while not self.stop:
            st = await self.bridge.status()
            if not st.playing:
                if st.state == "loading":
                    await asyncio.sleep(2)
                    continue
                await self.end_episode("the game left the play state")
                return
            tick, day = st.tick, st.day
            if st.colonists == 0 and day > self.episode.start_day:
                await self.end_episode("all colonists dead")
                return
            if self.force_end:
                reason, self.force_end = self.force_end, None
                await self.end_episode(reason)
                return
            if day - self.episode.start_day >= play.max_days:
                await self.end_episode(f"reached max_days ({play.max_days})")
                return
            if day != self.last_day:
                await self.day_rollover(day)
            if self.agent_paused:
                await asyncio.sleep(1)
                continue
            wake = await self.wake_trigger(tick)
            if wake is None:
                await asyncio.sleep(0.5)
                continue
            outcome = await self.step(wake)
            if outcome.episode_end:
                await self.end_episode(outcome.episode_end)
                return

    async def day_rollover(self, day: int) -> None:
        self.last_day = day
        self.save_episode()
        if self.s.play.autosave:
            try:
                await self.bridge.call("game.save", {"name": "agentv2-autosave"})
            except BridgeError as e:
                self.bus.emit("error", {"text": f"autosave: {e}"})
        play = self.s.play
        since_start, since_improve = day - self.episode.start_day, day - self.last_improve_day
        first = self.last_improve_day == self.episode.start_day and since_start >= play.first_improve_day
        if (first or since_improve >= play.improve_every_days) and not (self.improve_task and not self.improve_task.done()):
            self.last_improve_day = day
            self.improve_task = asyncio.create_task(self.improve(day), name="improve")
            self.improve_task.add_done_callback(self._report_failure)

    async def wake_trigger(self, tick: int) -> Wake | None:
        play = self.s.play
        if self.force:
            trigger, self.force = self.force, None
            return Wake(trigger, trigger.startswith("operator"))
        for alert in self.pending_alerts:
            if alert.wake:
                return Wake(f"watcher alert: {alert.text}", True)
        recently = tick - self.last_step_end_tick < play.event_cooldown_hours * TICKS_PER_HOUR
        kinds = set(play.wake_on_kinds) | self.turn_wake_on
        for e in self.pending_events:
            kind = e.get("kind")
            if kind in play.critical_kinds:
                return Wake(f"event: {kind}: {e.get('text', '')}", True)
            if kind in kinds and not recently:
                return Wake(f"event: {kind}: {e.get('text', '')}", False)
        if alert := await self.game_alert(tick):
            return alert
        if tick >= self.next_wake_tick:
            return Wake("scheduled check-in", False)
        return None

    async def game_alert(self, tick: int) -> Wake | None:
        if time.monotonic() - self._alerts_read < 5:
            return None
        self._alerts_read = time.monotonic()
        try:
            alerts = await self.bridge.call("state.alerts")
        except BridgeError:
            return None
        play, wake, live = self.s.play, None, set()
        for a in alerts or []:
            label, priority = str(a.get("label", "")), str(a.get("priority", ""))
            live.add(label)
            if priority not in play.alert_wake_priorities and "idle" not in label.lower():
                continue
            last = self.seen_alerts.get(label)
            if last is None or tick - last > play.alert_rewake_hours * TICKS_PER_HOUR:
                self.seen_alerts[label] = tick
                wake = wake or Wake(f"alert ({priority}): {label}", priority == "Critical")
        for label in set(self.seen_alerts) - live:
            del self.seen_alerts[label]
        return wake

    # ------------------------------------------------------------------ a think step

    async def step(self, wake: Wake) -> StepOutcome:
        assert self.deps is not None
        events, self.pending_events = self.pending_events, []
        alerts, self.pending_alerts = self.pending_alerts, []
        operator = list(self.operator_queue)
        wakeup = situation.Wakeup(wake.trigger, events, alerts, operator, self.numbers, self.brain.problems() | self.watchers.errors(), self.sandbox)
        report = situation.render(await situation.read(self.bridge), wakeup)
        self.numbers = report.numbers
        self.bus.emit("status", report.numbers)
        self.bus.emit("situation", {"trigger": wake.trigger, "changes": report.changes, "day": report.day, "hour": report.hour, "chars": len(report.text)})
        self.deps.turn = Turn()
        self.deps.urgent.clear()
        await self.set_speed(self.s.play.danger_think_speed if wake.urgent else self.s.play.think_speed)
        self.thinking = True
        self.bus.emit("status", {"phase": "thinking"})
        try:
            outcome = await self.think(report.text, wake)
        finally:
            self.thinking = False
            chosen = self.deps.turn.model_speed
            await self.set_speed(self.s.play.speed if chosen is None else max(1, chosen))
            self.bus.emit("status", {"phase": "playing", "model_speed": chosen})
        if self.deps.turn.replies:
            self.operator_queue.clear()
        elif self.operator_queue:
            self.force = "operator message"
        self.step_notes.append(outcome.notes)
        try:
            tick = (await self.bridge.status()).tick
        except BridgeError:
            tick = self.status.tick
        play = self.s.play
        hours = outcome.end.wake_in_hours if outcome.end and outcome.end.wake_in_hours else play.wake_hours
        floor = 0.5 if wake.urgent or self.deps.turn.model_speed is not None else play.min_wake_hours
        self.turn_wake_on = set(outcome.end.wake_on) if outcome.end else set()
        self.last_step_end_tick = tick
        self.next_wake_tick = tick + int(max(floor, min(play.max_wake_hours, hours)) * TICKS_PER_HOUR)
        return outcome

    async def think(self, prompt: str, wake: Wake) -> StepOutcome:
        assert self.deps is not None
        self.step_no += 1
        telemetry = Telemetry(self.deps)
        self.deps.emit("think_start", {"trigger": wake.trigger, "step": self.step_no, "urgent": wake.urgent, "prompt_chars": len(prompt)})
        started = time.monotonic()
        outcome, usage = await self._run_director(prompt, telemetry)
        self.deps.emit("think_end", {"notes": outcome.notes, "calls": telemetry.calls, "elapsed": round(time.monotonic() - started, 1),
                                     "wake": outcome.end.model_dump() if outcome.end else None, "end_episode": outcome.episode_end,
                                     "requests": usage.get("requests"), "tokens": usage.get("total_tokens")})
        return outcome

    async def _run_director(self, prompt: str, telemetry: Telemetry, authored: bool = True) -> tuple[StepOutcome, dict[str, Any]]:
        assert self.deps is not None
        limits = UsageLimits(request_limit=self.s.play.max_requests + 5)
        with capture_run_messages() as captured:
            try:
                result = await self.agents.director.run(prompt, deps=self.deps, message_history=self.history or None,
                                                        conversation_id=self.episode.colony, event_stream_handler=telemetry, usage_limits=limits,
                                                        metadata={AUTHORED: authored})
            except UserError as e:
                if not authored or not self.brain.has_authored():
                    raise
                self.bus.emit("error", {"text": f"an authored capability broke the step; running without authored capabilities: {e}"})
                return await self._run_director(prompt, telemetry, authored=False)
            except AgentRunError as e:
                self.history = list(captured) or self.history
                error = f"{type(e).__name__}: {e}"
                self.bus.emit("error", {"text": f"think step failed: {error}"})
                return StepOutcome(notes=f"(step failed: {error})", error=error), {}
        self.history = result.all_messages()
        usage = {"requests": result.usage.requests, "total_tokens": result.usage.total_tokens}
        match result.output:
            case TurnEnd() as end:
                return StepOutcome(notes=end.notes, end=end), usage
            case EpisodeEnd(reason=reason):
                return StepOutcome(notes=reason, episode_end=reason), usage
        raise TypeError(f"unexpected director output {result.output!r}")

    async def set_speed(self, speed: int) -> None:
        try:
            if speed <= 0:
                await self.bridge.call("game.pause", {"paused": True})
            else:
                await self.bridge.call("game.speed", {"speed": speed})
                await self.bridge.call("game.pause", {"paused": False})
        except BridgeError as e:
            self.bus.emit("error", {"text": f"speed {speed}: {e}"})

    # ------------------------------------------------------------------ brain passes

    def _usage_stats(self) -> str:
        counts, errors = collections.Counter(), collections.Counter()
        for e in self.bus.since(self.improve_seq, limit=5000, kinds={"tool_call", "tool_result"}):
            if e["data"].get("stream") != "play":
                continue
            if e["kind"] == "tool_call":
                counts[e["data"]["name"]] += 1
            elif not e["data"].get("ok"):
                errors[e["data"]["name"]] += 1
        self.improve_seq = self.bus.last_seq
        return "\n".join(f"- {n}: {c}" + (f", {errors[n]} failed" if errors[n] else "") for n, c in counts.most_common(25)) or "(no tool calls)"

    async def _brain_pass(self, which: str, prompt: str, commit: str) -> str:
        assert self.deps is not None
        deps = self.deps.fork("improve" if which == "improver" else "reflect")
        agent = self.agents.improver if which == "improver" else self.agents.reflector
        deps.emit("think_start", {"trigger": commit, "step": 0, "urgent": False, "prompt_chars": len(prompt)})
        started = time.monotonic()
        telemetry = Telemetry(deps)
        limits = UsageLimits(request_limit=self.s.play.max_requests + 5)
        try:
            try:
                result = await agent.run(prompt, deps=deps, event_stream_handler=telemetry, usage_limits=limits, metadata={AUTHORED: True})
            except UserError as e:
                if not self.brain.has_authored():
                    raise
                self.bus.emit("error", {"text": f"{which}: an authored capability broke the pass; running without authored capabilities: {e}"})
                result = await agent.run(prompt, deps=deps, event_stream_handler=telemetry, usage_limits=limits, metadata={AUTHORED: False})
            notes = result.output.notes
        except Exception as e:  # noqa: BLE001 - a failed pass is reported; the game and the episode go on
            notes = f"(pass failed: {type(e).__name__}: {e})"
            self.bus.emit("error", {"text": f"{which}: {notes}\n{traceback.format_exc(limit=6)}"})
        deps.emit("think_end", {"notes": notes, "calls": telemetry.calls, "elapsed": round(time.monotonic() - started, 1)})
        await self.commit_brain(commit)
        return notes

    async def commit_brain(self, message: str) -> str | None:
        try:
            sha = await self.git.commit(message)
        except GitError as e:
            self.bus.emit("error", {"text": f"brain commit: {e}"})
            return None
        if sha:
            self.bus.emit("brain_change", {"kind": "git", "action": "commit", "sha": sha})
        return sha

    def _report_failure(self, task: asyncio.Task[None]) -> None:
        if not task.cancelled() and (error := task.exception()):
            self.bus.emit("error", {"text": f"{task.get_name()}: {error!r}\n" + "".join(traceback.format_exception(error, limit=6))})

    async def improve(self, day: int) -> None:
        prompt = (f"# Improvement pass, day {day} of episode {self.episode.number}\n\n## Your tool use since the last pass (calls, failures)\n"
                  f"{self._usage_stats()}\n\n## Recent step notes\n" + "\n".join(f"- {n}" for n in self.step_notes[-30:] if n)
                  + f"\n\n## Scores\n{self.scores.text(8)}")
        notes = await self._brain_pass("improver", prompt, f"episode {self.episode.number} day {day}: improvement pass")
        self.step_notes.append(f"[improvement pass day {day}] {notes}")

    async def end_episode(self, reason: str) -> None:
        self.bus.emit("status", {"phase": "reflecting"})
        await self.set_speed(0)
        if self.improve_task:
            await asyncio.wait({self.improve_task})
        st, summary = self.status, {}
        try:
            st = await self.bridge.status()
            summary = await self.bridge.call("state.summary")
        except BridgeError as e:
            self.bus.emit("error", {"text": f"final read: {e}"})
        days = max(st.day, self.last_day) - self.episode.start_day
        colonists = int(summary.get("colonists", st.colonists) or 0)
        assisted = st.assisted or self.sandbox
        total = score(days, colonists, self.deaths, float(summary.get("wealth", 0) or 0), float(summary.get("mood_avg", 0) or 0),
                      int(summary.get("research_done", 0) or 0), self.raids)
        self.bus.emit("log", {"text": f"episode {self.episode.number} over: {reason}; days={days} colonists={colonists} deaths={self.deaths} score={total}"})
        timeline = "\n".join(f"[{e.get('day', '?')}d {e.get('hour', '?')}h] {e.get('kind')}: {e.get('text', '')}" for e in self.timeline)[-14_000:]
        prompt = (f"# Episode {self.episode.number} reflection (seed {self.episode.seed})\n\nThis game is over ({reason}) after {days} days. Score {total}.\n\n## Timeline\n{timeline}\n\n"
                  "## Your step notes\n" + "\n".join(f"- {n}" for n in self.step_notes[-40:] if n)
                  + f"\n\n## What the operator said\n{self.brain.operator.tail(3000)}"
                  + f"\n\n## Scores\n{self.scores.text(12)}")
        notes = await self._brain_pass("reflector", prompt, f"episode {self.episode.number} ({self.episode.seed}): {reason}; score {total}")
        try:
            sha = await self.git.head()
        except GitError as e:
            self.bus.emit("error", {"text": f"brain head: {e}"})
            sha = ""
        self.scores.record({"episode": self.episode.number, "seed": self.episode.seed, "days": days, "colonists": colonists, "deaths": self.deaths,
                            "raids": self.raids, "wealth": summary.get("wealth"), "mood": summary.get("mood_avg"), "research": summary.get("research_done"),
                            "score": total, "assisted": assisted, "brain_sha": sha, "ended": reason, "notes": notes[:500]})
        self.save_episode(ended=True)
        await self.commit_brain(f"episode {self.episode.number}: score")
        self.bus.emit("episode_end", {"episode": self.episode.number, "score": total, "reason": reason, "assisted": assisted, "brain_sha": sha, "days": days})
        self.episode = Episode(number=self.episode.number)
        if not self.stop:
            await self.new_game()

    # ------------------------------------------------------------------ game switches

    async def apply_steward(self) -> None:
        st = self.s.steward
        try:
            await self.bridge.call("steward.enable", {"scorer": self.steward and st.scorer, "stock": self.steward and st.stock})
            await self.bridge.call("steward.orders.set", {"id": "all", "enabled": self.steward and st.orders})
        except BridgeError as e:
            self.bus.emit("error", {"text": f"steward: {e} (the mod keeps its own defaults)"})
        self.bus.emit("status", {"steward": self.steward})

    async def apply_sandbox(self, on: bool) -> None:
        self.sandbox = self.episode.sandbox = on
        await self.bridge.call("game.dev_mode", {"enabled": True, "god": on})
        if on:
            await self.bridge.call("dev.unlock_all_research")
        self.bus.emit("status", {"sandbox": on})


class Controls:
    """What the dashboard can change."""

    def __init__(self, runner: Runner) -> None:
        self.r = runner

    @property
    def paused(self) -> bool:
        return self.r.agent_paused

    @property
    def sandbox(self) -> bool:
        return self.r.sandbox

    @property
    def steward(self) -> bool:
        return self.r.steward

    @property
    def no_pause(self) -> bool:
        return self.r.s.play.danger_think_speed > 0

    async def pause(self) -> None:
        self.r.agent_paused = True
        self.r.bus.emit("log", {"text": "agent paused by the operator"})

    async def resume(self) -> None:
        self.r.agent_paused = False
        self.r.bus.emit("log", {"text": "agent resumed by the operator"})

    async def think_now(self) -> None:
        self.r.force = "the operator asked for a step"

    async def end_episode(self) -> None:
        self.r.force_end = "the operator ended the episode"

    async def set_no_pause(self, value: bool) -> None:
        self.r.s.play.danger_think_speed = 1 if value else 0

    async def set_sandbox(self, value: bool) -> None:
        await self.r.apply_sandbox(value)
        self.r.force = "sandbox switched " + ("on: experiment and learn" if value else "off: play normally")

    async def set_steward(self, value: bool) -> None:
        self.r.steward = value
        await self.r.apply_steward()
        self.r.force = "steward switched " + ("on: direct it through rw_steward_*" if value else "off: you set priorities and designations yourself")

    async def set_order(self, order_id: str, value: bool) -> Any:
        return await self.r.bridge.call("steward.orders.set", {"id": order_id, "enabled": value})

    async def set_rally(self, rect: list[int] | None) -> Any:
        return await self.r.bridge.call("steward.orders.rally", {"clear": True} if rect is None else {"rect": rect})

    async def kill(self) -> None:
        self.r.stop = True

    async def say(self, text: str) -> None:
        self.r.brain.operator.record(time.strftime("%Y-%m-%d %H:%M"), text)
        self.r.bus.emit("operator", {"text": text})
        self.r.operator_queue.append(text)
        if self.r.thinking and self.r.deps is not None:
            self.r.deps.urgent.append("## Message from the human operator\nAnswer it now with reply_to_operator, then continue.\n- " + text)
        else:
            self.r.force = "operator message"
