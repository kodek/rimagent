"""The fast loop's tools: the director sets the directive; the director and the brain passes read, label, test, replay,
promote and demote the policies."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel
from pydantic_ai import RunContext, ToolFailed
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import AgentToolset, FunctionToolset

from ..bridge import BridgeError
from ..deps import Deps
from ..events import LoopNote
from .directive import TICKS_PER_HOUR, Directive, Priority
from .engine import FastLoop, brief
from .gate import Gate
from .jev import JevError
from .store import Decision

GUIDE = '''The FAST LOOP runs your policies (brain/policies/<name>.yaml) beside you, all the time, with Jev: a fast judgment model
(about 0.3 s per decision; it answers yes/no, choice and score questions with probabilities; it cannot write text or do
math). It handles what you delegate; you stay in charge:
- set_directive(...) tells it what you want: the purpose, ranked priorities, never-rules, what to report to you, and
  guidance per policy domain. Without a valid directive the policies only watch. Renew it before it expires.
- A policy decides one kind of thing (events, letters, dialogs, posture). A new or edited policy starts in shadow: it
  logs what it would do and acts on nothing. Your own answers to letters, dialogs and posture label its decisions.
- promote_policy(name) moves it shadow -> canary -> active when its held-out labels agree; demote_policy stops it.
- loop_status, list_decisions, label_decisions, test_policy and replay_policy show and improve it. The skill
  fast-loop has the policy format.
The situation report's "Fast loop" section says what it did. Its escalations wake you: decide those yourself.'''


class Label(BaseModel):
    id: int
    truth: str
    note: str = ""


def _row(d: Decision, heldout: bool) -> dict[str, Any]:
    row = {"id": d.id, "policy": d.policy, "stage": d.stage, "thing": d.summary, "outcome": d.outcome, "chose": d.label,
           "confidence": d.confidence, "reason": d.reason, "answers": {k: brief(a) for k, a in d.answers.items()}, "options": d.options}
    if d.truth is not None:
        row["truth"] = "(held out)" if heldout else d.truth
    return row


@dataclass
class LoopTools(AbstractCapability[Deps]):
    loop: FastLoop
    gate: Gate | None

    def get_instructions(self) -> str:
        return GUIDE

    def get_toolset(self) -> AgentToolset[Deps]:
        toolset = FunctionToolset[Deps](id="fast_loop")
        loop, gate = self.loop, self.gate
        default_hours = loop.settings.directive_hours

        @toolset.tool
        async def set_directive(ctx: RunContext[Deps], purpose: str, priorities: list[Priority], never: list[str] | None = None,
                                report_when: list[str] | None = None, guidance: dict[str, str] | None = None,
                                hours: float | None = None) -> dict[str, Any]:
            """Set what the fast loop works toward; it replaces the old directive at once. Write literal, checkable
            sentences: Jev reads them as they are and cannot compare numbers.

            Args:
                purpose: The goal now, e.g. "Survive the first winter with all colonists".
                priorities: Most important first; each {name, statement}, e.g. {"name": "food", "statement": "Keep more than 5 days of meals."}.
                never: Rules no action may break, e.g. "Never accept a quest that sends away more than one colonist."
                report_when: Conditions the loop must report to you instead of acting, e.g. "A colonist could die."
                guidance: Advice per policy domain (the policy's domain or subject: letters, dialogs, posture, events).
                hours: In-game hours until it expires (default from loop.directive_hours).
            """
            if not ctx.deps.role.writes_game:
                raise ToolFailed("only the director sets the directive")
            try:
                tick = (await ctx.deps.bridge.status()).tick
            except BridgeError as e:
                raise ToolFailed(str(e)) from e
            old = ctx.deps.episode.directive
            directive = Directive(version=old.version + 1 if old else 1, base_tick=tick, expires_tick=tick + int((hours or default_hours) * TICKS_PER_HOUR),
                                  purpose=purpose, priorities=priorities, never=never or [], report_when=report_when or [], guidance=guidance or {})
            ctx.deps.episode.directive = directive
            ctx.deps.emit(LoopNote(text=f"directive {directive.line()}"))
            unknown = sorted(set(directive.guidance) - {p.spec.area for p in loop.policies().values() if p.spec})
            return {"directive": directive.line(), "note": "the fast loop follows it from its next tick"} | (
                {"warning": f"no policy has the domain {unknown}"} if unknown else {})

        @toolset.tool_plain
        async def loop_status() -> dict[str, Any]:
            """The fast loop: on or off, Jev's health and spend, the directive, and each policy with its stage and decision counts."""
            return loop.snapshot()

        @toolset.tool_plain
        async def list_decisions(policy: str | None = None, show: Literal["all", "unlabelled", "disagreements", "escalated"] = "all",
                           limit: int = 20) -> list[dict[str, Any]]:
            """Recent fast-loop decisions with Jev's answers. The labels of held-out decisions stay hidden: only the gate scores on them.

            Args:
                policy: Only this policy.
                show: unlabelled (label these), disagreements (the label differs from what it chose), escalated, or all.
                limit: How many, newest first.
            """
            where = {"all": "", "unlabelled": "truth is null", "disagreements": "truth is not null and truth != coalesce(label, 'none')",
                     "escalated": "outcome in ('escalated', 'shadow-escalate', 'escalation-held')"}[show]
            rows = loop.store.recent(policy, min(limit, 100) * (3 if show == "disagreements" else 1), where)
            out = [_row(d, loop.store.heldout(d.id)) for d in rows if not (show == "disagreements" and loop.store.heldout(d.id))]
            return out[:limit]

        @toolset.tool
        async def label_decisions(ctx: RunContext[Deps], labels: list[Label]) -> dict[str, Any]:
            """Say what the right answer was for fast-loop decisions: an option label, `escalate` (the director had to decide)
            or `none` (nothing to do). Judge with hindsight: what happened after it.

            Args:
                labels: [{id, truth, note}].
            """
            done, refused, missing = [], [], []
            for x in labels:
                try:
                    (done if loop.label(x.id, x.truth, ctx.deps.role.name, x.note) else refused).append(x.id)
                except LookupError:
                    missing.append(x.id)
            return {"labelled": done} | ({"kept_stronger_label": refused} if refused else {}) | ({"no_such_decision": missing} if missing else {})

        @toolset.tool_plain
        async def test_policy(name: str, events: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
            """Dry-run a policy on the live game now: what it would decide and why. Nothing is logged or done.

            Args:
                name: The policy file stem in brain/policies.
                events: Ledger events for an events policy (default: the last matching ones).
            """
            try:
                return await loop.dry_run(name, events)
            except (LookupError, JevError, BridgeError) as e:
                raise ToolFailed(str(e)) from e

        @toolset.tool_plain
        async def replay_policy(name: str) -> dict[str, Any]:
            """Run the policy file as it is now on the labelled decisions you can see, and compare with the labels and with
            what was decided then. Use it before and after an edit."""
            if gate is None:
                raise ToolFailed("the fast loop has no Jev client (jev.api_key)")
            try:
                return (await gate.replay_visible(name)).model_dump()
            except LookupError as e:
                raise ToolFailed(str(e)) from e

        @toolset.tool_plain
        async def promote_policy(name: str) -> dict[str, Any]:
            """Ask the gate to move a policy one stage up: shadow -> canary (agreement with the held-out labels) or canary ->
            active (canary actions without failures or wrong labels). It says what is missing when it refuses."""
            if gate is None:
                raise ToolFailed("the fast loop has no Jev client (jev.api_key)")
            try:
                return await gate.promote(name)
            except LookupError as e:
                raise ToolFailed(str(e)) from e

        @toolset.tool
        async def demote_policy(ctx: RunContext[Deps], name: str, to: Literal["shadow", "off"] = "shadow", why: str = "") -> str:
            """Stop a policy from acting (shadow: it still logs what it would do) or from running at all (off)."""
            try:
                loop.set_stage(name, to, f"{ctx.deps.role.name}: {why}".strip(": "))
            except LookupError as e:
                raise ToolFailed(str(e)) from e
            return f"{name} is {to}"

        return toolset
