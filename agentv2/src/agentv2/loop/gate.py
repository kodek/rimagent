"""The promotion gate: a policy version acts only on evidence, and the agent cannot write the evidence itself.

Replay asks Jev the questions of a policy file about logged decisions (the exact states Jev saw then) and compares its
verdicts with their labels. The agent replays on the labels it can see; the gate scores on the held-out labels only.

  shadow -> canary: enough held-out labels, and agreement with them at least gate.min_agreement
  canary -> active: gate.canary_actions actions taken, none failed, none labelled wrong
An edited policy file is a new version and starts in shadow again. The loop demotes an acting version whose actions are
labelled wrong (FastLoop._check_demotion)."""
from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from ..config import GateSettings
from .engine import FastLoop, evaluate
from .jev import Jev, JevError
from .spec import Policy, jev_questions
from .store import Decision
from .subjects import Entity


class Verdicts(BaseModel):
    policy: str
    digest: str
    labelled: int
    agree: int
    agreement: float | None
    would_act: int
    would_escalate: int
    changed: int = Field(description="decisions where this version decides differently from the logged one")
    failed: int = 0
    rows: list[dict[str, Any]] = Field(default_factory=list)


def predicted(policy: Policy, decision: Decision, answers: dict[str, Any], report_up: float) -> str:
    """What this version would do, in label terms: the option it acts with, `escalate`, or `none`."""
    assert policy.spec is not None, "only valid policies replay"
    entity = Entity(key=decision.entity, summary=decision.summary, state={}, options=tuple(decision.options))
    verdict = evaluate(policy.spec, entity, answers, report_up)
    match verdict.outcome:
        case "act":
            return str(verdict.label)
        case "escalate":
            return "escalate"
        case _:
            return "none"


async def replay(policy: Policy, decisions: list[Decision], jev: Jev, report_up: float, *, show_truth: bool) -> Verdicts:
    assert policy.spec is not None, "only valid policies replay"
    spec = policy.spec

    async def one(d: Decision) -> dict[str, Any]:
        directive = d.state.get("directive") if isinstance(d.state, dict) else None
        questions = jev_questions(spec, tuple(d.options), isinstance(directive, dict) and bool(directive.get("report_when")))
        try:
            reply = await jev.ask(d.state, questions)
        except JevError as e:
            return {"id": d.id, "error": str(e)}
        now = predicted(policy, d, reply.answers, report_up)
        row: dict[str, Any] = {"id": d.id, "summary": d.summary, "was": d.verdict, "now": now}
        if show_truth:
            row["truth"] = d.truth
        return row | {"agree": now == d.truth}

    rows = await asyncio.gather(*(one(d) for d in decisions))
    done = [r for r in rows if "error" not in r]
    agree = sum(r["agree"] for r in done)
    return Verdicts(policy=policy.name, digest=policy.digest, labelled=len(done), agree=agree, agreement=round(agree / len(done), 3) if done else None,
                    would_act=sum(r["now"] not in ("escalate", "none") for r in done), would_escalate=sum(r["now"] == "escalate" for r in done),
                    changed=sum(r["now"] != r["was"] for r in done), failed=len(rows) - len(done),
                    rows=[{k: v for k, v in r.items() if show_truth or k != "agree"} for r in rows][-30:])


class Gate:
    def __init__(self, loop: FastLoop, jev: Jev, settings: GateSettings, report_up: float) -> None:
        self.loop = loop
        self.jev = jev
        self.settings = settings
        self.report_up = report_up

    def _policy(self, name: str) -> Policy:
        policy = self.loop.policies().get(name)
        if policy is None:
            raise LookupError(f"no policy {name!r}; have {sorted(self.loop.policies())}")
        if policy.spec is None:
            raise LookupError(f"policy {name} is invalid: {policy.error}")
        return policy

    async def replay_visible(self, name: str) -> Verdicts:
        """This version on the labelled decisions the agent can see (not the held-out ones)."""
        policy = self._policy(name)
        return await replay(policy, self.loop.store.labelled(name, heldout=False)[-60:], self.jev, self.report_up, show_truth=True)

    async def promote(self, name: str) -> dict[str, Any]:
        policy = self._policy(name)
        stage = self.loop.stage(policy)
        if stage in ("off", "shadow"):
            return await self._to_canary(policy)
        if stage == "canary":
            return self._to_active(policy)
        return {"promoted": False, "stage": stage, "why": "it is already active"}

    async def _to_canary(self, policy: Policy) -> dict[str, Any]:
        heldout = self.loop.store.labelled(policy.name, heldout=True)
        if len(heldout) < self.settings.min_heldout:
            return {"promoted": False, "stage": self.loop.stage(policy),
                    "why": f"{len(heldout)} held-out labels; the gate needs {self.settings.min_heldout}. Label more decisions of this policy: "
                           "your own answers to its escalations and to what it watched label them, and label_decisions adds more"}
        verdicts = await replay(policy, heldout, self.jev, self.report_up, show_truth=False)
        evidence = verdicts.model_dump(exclude={"rows"})
        if verdicts.failed or verdicts.agreement is None or verdicts.agreement < self.settings.min_agreement:
            return {"promoted": False, "stage": self.loop.stage(policy), "evidence": evidence,
                    "why": f"agreement with the held-out labels {verdicts.agreement} < {self.settings.min_agreement}"
                           + (f", {verdicts.failed} replays failed" if verdicts.failed else "")}
        self.loop.set_stage(policy.name, "canary", f"held-out agreement {verdicts.agreement} on {verdicts.labelled} labels", evidence)
        return {"promoted": True, "stage": "canary", "evidence": evidence,
                "next": f"it acts {self.settings.canary_actions} times; then promote_policy again"}

    def _to_active(self, policy: Policy) -> dict[str, Any]:
        counts = self.loop.store.counts(policy.name, policy.digest)
        wrong = [d.id for d in self.loop.store.recent(policy.name, 200, where="outcome = 'acted' and truth is not null", digest=policy.digest)
                 if d.truth != d.label]
        evidence = {"acted": counts.get("acted", 0), "failed": counts.get("failed", 0), "labelled_wrong": wrong}
        if counts.get("acted", 0) < self.settings.canary_actions or counts.get("failed", 0) or wrong:
            return {"promoted": False, "stage": "canary", "evidence": evidence,
                    "why": f"needs {self.settings.canary_actions} actions with none failed and none labelled wrong"}
        self.loop.set_stage(policy.name, "active", f"{evidence['acted']} canary actions, none failed or labelled wrong", evidence)
        return {"promoted": True, "stage": "active", "evidence": evidence}
