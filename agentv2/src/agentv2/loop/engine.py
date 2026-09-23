"""The fast loop: the agent's policies, run beside the director on the runner's asyncio loop.

Each tick it runs the policies that are due (a trigger event arrived, or their cadence came), asks Jev about each entity
with the director's directive in the state, and turns the answers into an action, an escalation to the director, or
nothing. A policy in `shadow` only logs what it would do; `canary` acts a few times; `active` acts. It never waits for
the director: it runs on the newest directive, and without a valid one it only watches.

It claims the ledger events that an acting policy owns (a dialog it will answer), so they do not wake the director; a
claim it cannot resolve is released and escalated. The director's own answers (on the bus) lease the thing to the
director and become labels for the loop's decisions on it."""
from __future__ import annotations

import asyncio
import collections
import hashlib
import json
import re
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from ..bridge import Bridge, BridgeError, GameStatus
from ..bus import Bus
from ..config import LoopSettings
from ..episode import Episode
from ..events import LoopDecision, LoopNote
from .directive import TICKS_PER_HOUR, Directive
from .jev import (
    Answer,
    ChoiceAnswer,
    Jev,
    JevError,
    JevUnavailable,
    NoulAnswer,
    ScoreAnswer,
)
from .spec import REPORT_UP, Policy, PolicyRepository, PolicySpec, jev_questions
from .store import LoopStore, Stage
from .subjects import POSTURES, SUBJECTS, Entity, Screen, colony_features

DIRECTOR_CALLS = {"rw_ui_letter", "rw_ui_dialog", "rw_steward_posture"}
LABEL_WINDOW_S = 600
_CHOSE = re.compile(r"^chose '(.*)'$")


@dataclass(frozen=True)
class Escalation:
    policy: str
    key: str
    text: str
    urgent: bool


@dataclass
class Claim:
    event: dict[str, Any]
    policy: str
    key: str | None
    deadline: float
    state: Literal["pending", "resolved", "released"] = "pending"


@dataclass(frozen=True)
class Verdict:
    outcome: Literal["act", "escalate", "skip", "note"]
    label: str | None = None
    confidence: float | None = None
    reason: str = ""


def evaluate(spec: PolicySpec, entity: Entity, answers: dict[str, Answer], report_up: float) -> Verdict:
    """Jev's answers and the policy's rule -> what to do. The directive's report_when check comes first."""
    d = spec.decide
    if isinstance(a := answers.get(REPORT_UP), NoulAnswer) and a.noul >= report_up:
        return Verdict("escalate", reason=f"matches directive.report_when ({a.noul:.2f})")
    for name, limit in d.escalate_if.items():
        a = answers[name]
        value = a.noul if isinstance(a, NoulAnswer) else a.score if isinstance(a, ScoreAnswer) else None
        if value is not None and value >= limit:
            return Verdict("escalate", reason=f"{name} {value:.2f} >= {limit}")
    if d.act_with is None:
        return Verdict("note")
    choice = answers[d.act_with]
    assert isinstance(choice, ChoiceAnswer), f"{d.act_with} is a choice question"
    label, confidence = choice.choice, choice.confidence
    if label == "escalate":
        return Verdict("escalate", label, confidence, "Jev chose escalate")
    if label == "none":
        return Verdict("skip", label, confidence, "Jev chose none")
    if confidence < d.min_confidence:
        return Verdict("escalate" if d.on_doubt == "escalate" else "skip", label, confidence, f"confidence {confidence:.2f} < {d.min_confidence}")
    for name, limit in d.vetoes.items():
        veto = answers[name]
        if isinstance(veto, NoulAnswer) and veto.noul >= limit:
            return Verdict("escalate", label, confidence, f"veto {name} {veto.noul:.2f} >= {limit}")
    if entity.current is not None and label == entity.current:
        return Verdict("skip", label, confidence, "no change")
    return Verdict("act", label, confidence)


@dataclass
class _Report:
    outcomes: collections.Counter[tuple[str, str]] = field(default_factory=collections.Counter)
    lines: list[str] = field(default_factory=list)


class FastLoop:
    def __init__(self, settings: LoopSettings, jev: Jev | None, bridge: Bridge, bus: Bus, store: LoopStore, policies_dir: Path,
                 episode: Callable[[], Episode], status: Callable[[], GameStatus], critical_kinds: set[str],
                 on_escalate: Callable[[list[Escalation]], Coroutine[Any, Any, None]], clock: Callable[[], float] = time.monotonic) -> None:
        self.settings = settings
        self.jev = jev
        self.bridge = bridge
        self.bus = bus
        self.store = store
        self.repository = PolicyRepository(policies_dir)
        self.screen = Screen(bridge, clock)
        self.episode = episode
        self.status = status
        self.critical_kinds = critical_kinds
        self.on_escalate = on_escalate
        self.on = settings.enabled
        self._clock = clock
        self._bus = bus.subscribe()
        self._events: collections.deque[dict[str, Any]] = collections.deque(maxlen=1000)
        self._recent: collections.deque[dict[str, Any]] = collections.deque(maxlen=50)
        self._claims: dict[int, Claim] = {}
        self._stages: dict[tuple[str, str], Stage] = {}
        self._problems: dict[str, str] = {}
        self._scanned = -1e9
        self._down: str | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self.reset()

    # ------------------------------------------------------------------ state

    def reset(self) -> None:
        """A new game: forget what belongs to the old one."""
        self._events.clear()
        self._claims.clear()
        self._decided: dict[tuple[str, str], str] = {}
        self._ran: dict[str, float] = {}
        self._ran_tick: dict[str, int] = {}
        self._acted: dict[tuple[str, str], int] = {}
        self._action_ticks: dict[str, collections.deque[int]] = collections.defaultdict(collections.deque)
        self._call_times: dict[str, collections.deque[float]] = collections.defaultdict(collections.deque)
        self._leases: dict[str, tuple[str, int]] = {}
        self._escalated: set[tuple[str, str]] = set()
        self._escalation_ticks: collections.deque[int] = collections.deque()
        self._suppressed = 0
        self._director_calls: dict[str, tuple[str, dict[str, Any]]] = {}
        self._own_dialog_answers: collections.deque[tuple[str, float]] = collections.deque(maxlen=20)
        self._report = _Report()

    @property
    def running(self) -> bool:
        return self.on and self.jev is not None

    def policies(self) -> dict[str, Policy]:
        if self._clock() - self._scanned >= 2:
            self._scanned = self._clock()
            self.repository.scan()
        return self.repository.loaded

    def stage(self, policy: Policy) -> Stage:
        key = (policy.name, policy.digest)
        if key not in self._stages:
            self._stages[key] = self.store.stage(policy.name, policy.digest)
        return self._stages[key]

    def set_stage(self, name: str, stage: Stage, note: str, evidence: dict[str, Any] | None = None) -> Stage:
        policy = self.policies().get(name)
        if policy is None or policy.spec is None:
            raise LookupError(f"no valid policy {name!r}")
        self.store.set_stage(name, policy.digest, stage, note, evidence)
        self._stages[(name, policy.digest)] = stage
        self._note(f"{name} is now {stage}: {note}", name)
        if stage in ("off", "shadow"):
            self._release([c for c in self._claims.values() if c.policy == name and c.state == "pending"], f"{name} stopped acting")
        return stage

    def problems(self) -> dict[str, str]:
        out = {f"policy {p.name}": p.error for p in self.policies().values() if p.error}
        return out | {f"policy {k}": v for k, v in self._problems.items()}

    def directive(self, tick: int | None = None) -> Directive | None:
        """The directive in force: None when there is none or it expired."""
        directive = self.episode().directive
        tick = self.status().tick if tick is None else tick
        return directive if directive and not directive.expired(tick) else None

    # ------------------------------------------------------------------ the poller's side

    def observe(self, events: list[dict[str, Any]]) -> set[int]:
        """New ledger events, from the poller. Returns the seqs of the events an acting policy claims: they do not wake the
        director unless the loop releases them."""
        self._events.extend(events)
        self._recent.extend(events)
        if not self._can_act():
            return set()
        acting = [p for p in self.policies().values() if p.spec and p.spec.claims and self.stage(p) in ("canary", "active")
                  and (p.spec.safe_without_directive or self.directive() is not None)]
        claimed = set()
        for e in events:
            seq = e.get("seq")
            for p in acting:
                subject = SUBJECTS[p.spec.subject]  # type: ignore[union-attr]
                if isinstance(seq, int) and e.get("kind") in p.spec.claims and subject.accepts(e):  # type: ignore[union-attr]
                    self._claims[seq] = Claim(e, p.name, subject.claim_key(e), self._clock() + self.settings.claim_timeout_s)
                    claimed.add(seq)
                    break
        return claimed

    def holds(self, event: dict[str, Any]) -> bool:
        claim = self._claims.get(event.get("seq", -1))
        return claim is not None and claim.state != "released"

    def _can_act(self) -> bool:
        return self.running and self.status().playing and self.jev is not None and self.jev.health().available

    # ------------------------------------------------------------------ the loop

    async def run(self, stopped: Callable[[], bool]) -> None:
        while not stopped():
            try:
                await self.tick_once()
            except Exception as e:  # noqa: BLE001 - the loop reports and keeps running; the director and the Steward go on
                self._note(f"fast loop error: {type(e).__name__}: {e}")
            await asyncio.sleep(self.settings.tick_s)

    async def tick_once(self) -> None:
        self._harvest_director_calls()
        events = list(self._events)
        self._events.clear()
        self._harvest_dialog_answers(events)
        st = self.status()
        if not (self.running and st.playing):
            self._release([c for c in self._claims.values() if c.state == "pending"], "the fast loop is off")
            return
        assert self.jev is not None, "running means a Jev client"
        if not (health := self.jev.health()).available:
            if self._down is None:
                self._down = health.reason
                self._note(f"Jev is unavailable, the loop waits: {health.reason}")
            self._release([c for c in self._claims.values() if c.state == "pending"], f"Jev is unavailable: {health.reason}")
            return
        if self._down is not None:
            self._down = None
            self._note("Jev is available again")
        directive = self.directive(st.tick)
        due = [(p, hits) for p in self.policies().values() if (hits := self._due(p, events, st.tick)) is not None]
        await asyncio.gather(*(self._run_policy(p, hits, st.tick, directive) for p, hits in due))
        now = self._clock()
        self._release([c for c in self._claims.values() if c.state == "pending" and c.deadline < now], "no decision in time")
        for seq in [s for s, c in self._claims.items() if c.state != "pending" and c.deadline < now - 600]:
            del self._claims[seq]

    def _due(self, policy: Policy, events: list[dict[str, Any]], tick: int) -> list[dict[str, Any]] | None:
        spec = policy.spec
        if spec is None or self.stage(policy) == "off":
            return None
        hits = [e for e in events if e.get("kind") in spec.triggers.events]
        pending = any(c.policy == policy.name and c.state == "pending" for c in self._claims.values())
        t = spec.triggers
        timed = (t.every_seconds is not None and self._clock() - self._ran.get(policy.name, -1e9) >= t.every_seconds) or (
            t.every_hours is not None and tick - self._ran_tick.get(policy.name, -10**9) >= t.every_hours * TICKS_PER_HOUR)
        return hits if hits or pending or timed else None

    async def _run_policy(self, policy: Policy, hits: list[dict[str, Any]], tick: int, directive: Directive | None) -> None:
        spec = policy.spec
        assert spec is not None, "only valid policies run"
        self._ran[policy.name], self._ran_tick[policy.name] = self._clock(), tick
        subject = SUBJECTS[spec.subject]
        claimed = any(c.policy == policy.name and c.state == "pending" for c in self._claims.values())
        if subject.reads and (hits or claimed):
            self.screen.forget(subject.reads)
        try:
            entities = await subject.entities(self.screen, hits, self.settings)
            summary = await self.screen.read("state.summary", self.settings.summary_max_age_s) if spec.features else {}
        except BridgeError as e:
            self._problems[policy.name] = f"reading the game: {e}"
            self._release([c for c in self._claims.values() if c.policy == policy.name and c.state == "pending"], f"reading the game failed: {e}")
            return
        self._problems.pop(policy.name, None)
        keys = {e.key for e in entities}
        self._release([c for c in self._claims.values() if c.policy == policy.name and c.state == "pending" and c.key not in keys],
                      f"nothing for {policy.name} to decide")
        fresh = []
        for entity in entities:
            if self._leased(entity.key, tick):
                continue
            continuous = entity.current is not None
            seen = _digest(policy.digest, entity.state, *([colony_features(summary, spec.features), tick // TICKS_PER_HOUR,
                                                          [e.get("seq") for e in hits]] if continuous else []))
            if self._decided.get((policy.name, entity.key)) != seen:
                fresh.append((entity, seen))
        await asyncio.gather(*(self._decide(policy, entity, seen, tick, directive, summary) for entity, seen in fresh))

    async def _decide(self, policy: Policy, entity: Entity, seen: str, tick: int, directive: Directive | None, summary: dict[str, Any]) -> None:
        spec = policy.spec
        assert spec is not None and self.jev is not None, "only valid policies run, with Jev"
        if not self._take_call(policy.name, spec.budget.calls_per_minute):
            return
        state = _state(spec, entity, directive, summary)
        questions = jev_questions(spec, entity.options, bool(directive and directive.report_when))
        started = self._clock()
        try:
            reply = await self.jev.ask(state, questions)
        except JevUnavailable as e:
            self._release(self._claims_on(policy.name, entity.key), f"Jev is unavailable: {e}")
            return
        except JevError as e:
            self._problems[policy.name] = f"Jev: {e}"
            self._release(self._claims_on(policy.name, entity.key), f"Jev failed: {e}")
            return
        ms = round((self._clock() - started) * 1000, 1)
        self._decided[(policy.name, entity.key)] = seen
        verdict = evaluate(spec, entity, reply.answers, self.settings.report_up_threshold)
        stage, why_not = self._acting_stage(policy, spec, directive)
        if verdict.outcome == "act" and (reason := self._held_back(policy.name, spec, entity.key, tick)):
            verdict = Verdict("skip", verdict.label, verdict.confidence, reason)
        decision_id = self.store.record(tick=tick, colony=self.episode().colony, policy=policy.name, digest=policy.digest, stage=stage,
                                        entity=entity.key, summary=entity.summary, options=list(entity.options), state=state,
                                        questions={k: q.model_dump(mode="json", exclude_none=True) for k, q in questions.items()},
                                        answers={k: a.model_dump(mode="json") for k, a in reply.answers.items()}, label=verdict.label,
                                        confidence=verdict.confidence, outcome="pending", reason=verdict.reason, ms=ms)
        match verdict.outcome, stage:
            case "act", "canary" | "active":
                outcome = await self._act(policy, spec, entity, verdict, decision_id, tick)
            case "escalate", "canary" | "active":
                delivered = await self._escalate(policy.name, entity, f"{verdict.reason}{_options(reply.answers.get(spec.decide.act_with or ''))}",
                                                 decision_id, tick)
                outcome = "escalated" if delivered else "escalation-held"
            case "act" | "escalate", _:
                outcome = "shadow" if verdict.outcome == "act" else "shadow-escalate"
            case _:
                outcome = "skipped" if verdict.outcome == "skip" else "noted"
        reason = verdict.reason + (f"; {why_not}" if why_not and outcome.startswith("shadow") else "")
        if outcome not in ("acted", "failed"):
            self.store.finish(decision_id, outcome, reason)
        claims = self._claims_on(policy.name, entity.key)
        if outcome in ("acted", "escalated"):
            for claim in claims:
                claim.state = "resolved"
        else:
            self._release(claims, f"{policy.name}: {outcome}")
        self._report.outcomes[(policy.name, outcome)] += 1
        if outcome in ("acted", "escalated", "failed", "shadow", "shadow-escalate"):
            self._report.lines.append(f"{policy.name} [{stage}] {entity.summary}: {outcome}"
                                      + (f" {verdict.label} ({verdict.confidence:.2f})" if verdict.label and verdict.confidence is not None else "")
                                      + (f" - {reason}" if reason else ""))
        self.bus.emit(LoopDecision(id=decision_id, policy=policy.name, stage=stage, entity=entity.key, summary=entity.summary, outcome=outcome,
                                   label=verdict.label, confidence=verdict.confidence, reason=reason, ms=ms))

    def _acting_stage(self, policy: Policy, spec: PolicySpec, directive: Directive | None) -> tuple[Stage, str | None]:
        stage = self.stage(policy)
        if stage in ("canary", "active") and directive is None and not spec.safe_without_directive:
            return "shadow", "no valid directive"
        if stage == "canary" and self.store.counts(policy.name, policy.digest).get("acted", 0) >= self.settings.gate.canary_actions:
            return "shadow", "its canary actions are used; promote_policy decides"
        return stage, None

    def _held_back(self, name: str, spec: PolicySpec, key: str, tick: int) -> str | None:
        last = self._acted.get((name, key))
        if last is not None and tick - last < spec.decide.dwell_hours * TICKS_PER_HOUR:
            return f"acted {(tick - last) / TICKS_PER_HOUR:.1f} h ago (dwell {spec.decide.dwell_hours} h)"
        ticks = self._action_ticks[name]
        while ticks and tick - ticks[0] > TICKS_PER_HOUR:
            ticks.popleft()
        if len(ticks) >= spec.budget.actions_per_hour:
            return f"action budget: {len(ticks)} actions in the last in-game hour"
        return None

    async def _act(self, policy: Policy, spec: PolicySpec, entity: Entity, verdict: Verdict, decision_id: int, tick: int) -> str:
        subject = SUBJECTS[spec.subject]
        assert subject.method is not None and verdict.label is not None, "an acting subject and a label"
        if subject.reads:
            self.screen.forget(subject.reads)
        now = {e.key: e for e in await subject.entities(self.screen, [], self.settings)}
        if entity.key not in now:
            self.store.finish(decision_id, "skipped", "it was gone before the loop acted")
            return "skipped"
        params = subject.call(now[entity.key], verdict.label, dict(spec.params))
        try:
            result = await self.bridge.call(subject.method, params, timeout_ms=self.settings.action_timeout_ms)
        except BridgeError as e:
            self.store.finish(decision_id, "failed", str(e), {"method": subject.method, "params": params})
            self._problems[policy.name] = f"{subject.method}: {e}"
            return "failed"
        finally:
            if subject.reads:
                self.screen.forget(subject.reads)
        self.store.finish(decision_id, "acted", None, {"method": subject.method, "params": params}, result)
        self._acted[(policy.name, entity.key)] = tick
        self._action_ticks[policy.name].append(tick)
        if spec.subject == "dialogs":
            self._own_dialog_answers.append((verdict.label, self._clock()))
        return "acted"

    async def dry_run(self, name: str, events: list[dict[str, Any]] | None = None, limit: int = 8) -> list[dict[str, Any]]:
        """What a policy would decide now about the live game, without logging or acting. An events policy uses `events`
        or the last matching ledger events."""
        policy = self.policies().get(name)
        if policy is None or policy.spec is None:
            raise LookupError(f"no valid policy {name!r}" + (f": {policy.error}" if policy else f"; have {sorted(self.policies())}"))
        jev = self.jev
        if jev is None:
            raise LookupError("the fast loop has no Jev client (jev.api_key)")
        spec, subject = policy.spec, SUBJECTS[policy.spec.subject]
        directive = self.directive()
        hits = events if events is not None else [e for e in self._recent if e.get("kind") in spec.triggers.events][-limit:]
        entities = (await subject.entities(self.screen, hits, self.settings))[:limit]
        summary = await self.screen.read("state.summary", self.settings.summary_max_age_s) if spec.features else {}

        async def one(entity: Entity) -> dict[str, Any]:
            questions = jev_questions(spec, entity.options, bool(directive and directive.report_when))
            reply = await jev.ask(_state(spec, entity, directive, summary), questions)
            verdict = evaluate(spec, entity, reply.answers, self.settings.report_up_threshold)
            return {"entity": entity.summary, "would": verdict.outcome, "label": verdict.label, "confidence": verdict.confidence,
                    "reason": verdict.reason, "answers": {k: brief(a) for k, a in reply.answers.items()}}

        return list(await asyncio.gather(*(one(e) for e in entities))) or [{"note": f"nothing for {name} to decide now"}]

    # ------------------------------------------------------------------ escalations and claims

    async def _escalate(self, policy: str, entity: Entity, why: str, decision_id: int, tick: int) -> bool:
        """Tell the director; False when the escalation was held back by the rate limit."""
        if (policy, entity.key) in self._escalated:
            return True
        while self._escalation_ticks and tick - self._escalation_ticks[0] > TICKS_PER_HOUR:
            self._escalation_ticks.popleft()
        if len(self._escalation_ticks) >= self.settings.escalations_per_hour:
            self._suppressed += 1
            return False
        self._escalated.add((policy, entity.key))
        self._escalation_ticks.append(tick)
        urgent = entity.key.startswith("dialog:") or any(c.event.get("kind") in self.critical_kinds for c in self._claims_on(policy, entity.key))
        text = f"{entity.summary}: {why} (decision {decision_id}; decide it yourself, your answer becomes its label)"
        await self.on_escalate([Escalation(policy, entity.key, text, urgent)])
        return True

    def _claims_on(self, policy: str, key: str) -> list[Claim]:
        return [c for c in self._claims.values() if c.policy == policy and c.key == key and c.state == "pending"]

    def _release(self, claims: list[Claim], reason: str) -> None:
        """The loop will not answer these events: the normal wake rules apply to them again, and a running step hears
        at once about a critical one."""
        urgent = []
        for claim in claims:
            claim.state = "released"
            if claim.event.get("kind") in self.critical_kinds:
                urgent.append(Escalation(claim.policy, claim.key or "", f"{claim.event.get('kind')}: {claim.event.get('text', '')} "
                                                                         f"(the fast loop did not handle it: {reason})", True))
        if urgent:
            task = asyncio.get_running_loop().create_task(self.on_escalate(urgent))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    # ------------------------------------------------------------------ the director's own answers

    def _harvest_director_calls(self) -> None:
        while not self._bus.empty():
            record = self._bus.get_nowait()
            data = record["data"]
            if data.get("stream") != "play":
                continue
            if record["kind"] == "tool_call" and data.get("name") in DIRECTOR_CALLS:
                self._director_calls[data["id"]] = (data["name"], data.get("args") or {})
            elif record["kind"] == "tool_result" and (call := self._director_calls.pop(data.get("id"), None)) and data.get("ok"):
                self._director_did(*call)

    def _director_did(self, name: str, args: dict[str, Any]) -> None:
        tick, since = self.status().tick, time.time() - LABEL_WINDOW_S
        match name:
            case "rw_ui_letter":
                key = f"letter:{args.get('id')}"
                self._leases[key] = ("director", tick + TICKS_PER_HOUR)
                if args.get("action") == "choose" and (d := self.store.latest(key, since_t=since)):
                    self._label(d.id, _option(d.options, args.get("choice")), "director", "the director answered the letter")
            case "rw_steward_posture":
                self._leases["colony"] = ("director", tick + int(self.settings.director_lease_hours * TICKS_PER_HOUR))
                preset = "normal" if args.get("clear") else args.get("preset") or args.get("label")
                if preset in POSTURES and (d := self.store.latest("colony", since_t=since)):
                    self._label(d.id, str(preset), "director", "the director set the posture")

    def _harvest_dialog_answers(self, events: list[dict[str, Any]]) -> None:
        for e in events:
            if e.get("kind") != "dialog_answered" or not (m := _CHOSE.match(str(e.get("text", "")))):
                continue
            label, now = m[1], self._clock()
            own = next((x for x in self._own_dialog_answers if x[0] == label and now - x[1] < 30), None)
            if own:
                self._own_dialog_answers.remove(own)
                continue
            since = time.time() - LABEL_WINDOW_S
            for d in self.store.recent(where="entity like 'dialog:%' and truth is null and outcome != 'acted'", limit=20):
                if d.t >= since and label in d.options:
                    self._label(d.id, label, "director", "the director answered the dialog")
                    break

    def _leased(self, key: str, tick: int) -> bool:
        lease = self._leases.get(key)
        return lease is not None and tick < lease[1]

    def label(self, decision_id: int, truth: str, source: str, note: str = "") -> bool:
        return self._label(decision_id, truth, source, note)

    def _label(self, decision_id: int, truth: str, source: str, note: str) -> bool:
        if not self.store.set_truth(decision_id, truth, source, note):
            return False
        d = self.store.get(decision_id)
        if d and d.outcome == "acted" and d.label != truth:
            self._check_demotion(d.policy, d.digest)
        return True

    def _check_demotion(self, name: str, digest: str) -> None:
        policy = self.policies().get(name)
        if policy is None or policy.digest != digest or self.stage(policy) not in ("canary", "active"):
            return
        wrong = [d for d in self.store.recent(name, 10, where="outcome = 'acted' and truth is not null", digest=digest) if d.truth != d.label]
        if len(wrong) >= self.settings.gate.demote_after_wrong:
            self.set_stage(name, "shadow", f"demoted: {len(wrong)} of its actions were labelled wrong",
                           {"wrong": [{"id": d.id, "label": d.label, "truth": d.truth} for d in wrong]})

    # ------------------------------------------------------------------ reports

    def _take_call(self, name: str, per_minute: int) -> bool:
        times, now = self._call_times[name], self._clock()
        while times and now - times[0] > 60:
            times.popleft()
        if len(times) >= per_minute:
            return False
        times.append(now)
        return True

    def _note(self, text: str, policy: str | None = None) -> None:
        self._report.lines.append(text)
        self.bus.emit(LoopNote(text=text, policy=policy))

    def report(self) -> str | None:
        """What the loop did since the last call, for the director's situation report."""
        tick = self.status().tick
        directive = self.episode().directive
        if directive is None:
            head = "directive: NONE. Acting policies only watch until you call set_directive(...)"
        elif directive.expired(tick):
            head = f"directive: EXPIRED ({directive.line()}). Acting policies only watch; set a new one with set_directive(...)"
        else:
            head = f"directive {directive.line()}"
        rows = []
        for p in self.policies().values():
            if p.spec is None:
                rows.append(f"- {p.name}: INVALID: {p.error}")
                continue
            done = {o: n for (name, o), n in self._report.outcomes.items() if name == p.name}
            rows.append(f"- {p.name} [{self.stage(p)}] ({p.spec.subject}): " + (", ".join(f"{n} {o}" for o, n in sorted(done.items())) or "no decisions"))
        if not self.running:
            head += "\nthe fast loop is OFF" + ("" if self.jev else " (no Jev key: jev.api_key or TYPESAFE_API_KEY)")
        elif self._down:
            head += f"\nJev is UNAVAILABLE: {self._down}"
        lines = self._report.lines[-12:]
        if self._suppressed:
            lines.append(f"{self._suppressed} more escalations were held back (loop.escalations_per_hour)")
        self._report, self._suppressed = _Report(), 0
        return "\n".join([head, *rows, *(f"- {x}" for x in lines)])

    def pass_summary(self, min_heldout: int) -> str:
        """For the brain passes: each policy's stage, counts and labels, and what is missing for its next stage."""
        directive = self.episode().directive
        lines = [f"directive: {directive.line() if directive else 'none set'}"]
        for p in self.policies().values():
            if p.spec is None:
                lines.append(f"- {p.name}: INVALID: {p.error}")
                continue
            visible = self.store.labelled(p.name, heldout=False)
            heldout = len(self.store.labelled(p.name, heldout=True))
            disagree = sum(d.truth != d.verdict for d in visible)
            counts = ", ".join(f"{n} {o}" for o, n in sorted(self.store.counts(p.name, p.digest).items())) or "no decisions yet"
            lines.append(f"- {p.name} [{self.stage(p)}] ({p.spec.subject}): {counts}; {len(visible)} labels you can see "
                         f"({disagree} disagree with its verdict); held-out labels {heldout}/{min_heldout}")
        return "\n".join(lines)

    def snapshot(self) -> dict[str, Any]:
        """For the dashboard and loop_status."""
        policies = []
        for p in self.policies().values():
            row: dict[str, Any] = {"name": p.name, "digest": p.digest, "error": p.error}
            if p.spec:
                row |= {"subject": p.spec.subject, "stage": self.stage(p), "description": p.spec.description,
                        "decisions": self.store.counts(p.name, p.digest), "problem": self._problems.get(p.name)}
            policies.append(row)
        directive = self.episode().directive
        return {"on": self.on, "jev": self.jev.health().model_dump() if self.jev else None, "policies": policies,
                "directive": directive.model_dump() if directive else None,
                "directive_valid": self.directive() is not None, "claims": sum(c.state == "pending" for c in self._claims.values())}


def _state(spec: PolicySpec, entity: Entity, directive: Directive | None, summary: dict[str, Any]) -> dict[str, Any]:
    """What Jev sees: the directive's part for this policy, the colony features it asked for, and the thing itself."""
    state: dict[str, Any] = {"directive": directive.brief(spec.area) if directive else "none: the director has not set one"}
    if spec.features:
        state["colony"] = colony_features(summary, spec.features)
    return state | entity.state


def brief(answer: Answer | dict[str, Any]) -> Any:
    """One answer in a few characters: the yes probability, the choice and its confidence, or the expected score."""
    a = answer if isinstance(answer, dict) else answer.model_dump()
    match a.get("type"):
        case "noul":
            return round(a["noul"], 2)
        case "choice":
            return f"{a['choice']} ({a['confidence']:.2f})"
        case _:
            return round(a.get("score", 0), 2)


def _digest(*parts: Any) -> str:
    return hashlib.blake2b(json.dumps(parts, sort_keys=True, default=str).encode(), digest_size=8).hexdigest()


def _options(answer: Answer | None) -> str:
    if not isinstance(answer, ChoiceAnswer):
        return ""
    top = sorted(answer.probabilities.items(), key=lambda kv: -kv[1])[:3]
    return "; Jev: " + ", ".join(f"{k} {v:.2f}" for k, v in top)


def _option(options: list[str], choice: Any) -> str:
    if isinstance(choice, int) and 0 <= choice < len(options):
        return options[choice]
    text = str(choice)
    return next((o for o in options if o.lower() == text.lower()), text)
