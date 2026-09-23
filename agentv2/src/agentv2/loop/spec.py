"""A policy: one independent decision unit of the fast loop, written by the agent as `brain/policies/<name>.yaml`.

It names a subject (what it decides about), its triggers, the colony features and questions Jev gets, and the rule that
turns Jev's answers into an action, an escalation to the director, or nothing. The schema is strict, so a policy the
agent writes either validates or is reported as a brain problem; its content hash is its version."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    field_validator,
    model_validator,
)

from .jev import Choice, Noul, Question, Score
from .subjects import DEFAULT_FEATURES, FEATURES, SUBJECTS

REPORT_UP = "report_up"
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Triggers(Strict):
    events: list[str] = Field(default_factory=list)
    every_seconds: float | None = Field(default=None, gt=0)
    every_hours: float | None = Field(default=None, gt=0)


class QuestionSpec(Strict):
    type: Literal["noul", "choice", "score"]
    instructions: str
    criteria: dict[str, str | None] | list[str] | None = None
    options_from_subject: bool = False

    @field_validator("criteria", mode="before")
    @classmethod
    def _yaml_booleans(cls, value: Any) -> Any:
        """YAML reads an unquoted `true:` key as a boolean."""
        return {str(k).lower() if isinstance(k, bool) else k: v for k, v in value.items()} if isinstance(value, dict) else value


class Decide(Strict):
    act_with: str | None = None
    min_confidence: float = Field(default=0.6, ge=0, le=1)
    on_doubt: Literal["escalate", "skip"] = "escalate"
    vetoes: dict[str, float] = Field(default_factory=dict)
    escalate_if: dict[str, float] = Field(default_factory=dict)
    dwell_hours: float = Field(default=0, ge=0)


class Budget(Strict):
    calls_per_minute: int = Field(default=60, ge=1)
    actions_per_hour: int = Field(default=20, ge=0)


class PolicySpec(Strict):
    description: str
    subject: Literal["events", "letters", "dialogs", "posture"]
    domain: str | None = None
    triggers: Triggers
    claims: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=lambda: list(DEFAULT_FEATURES))
    questions: dict[str, QuestionSpec]
    decide: Decide = Field(default_factory=Decide)
    params: dict[str, JsonValue] = Field(default_factory=dict)
    budget: Budget = Field(default_factory=Budget)
    safe_without_directive: bool = False

    @property
    def area(self) -> str:
        return self.domain or self.subject

    @model_validator(mode="after")
    def _consistent(self) -> PolicySpec:
        subject = SUBJECTS[self.subject]
        problems = [f"unknown feature {f!r}; known: {', '.join(FEATURES)}" for f in self.features if f not in FEATURES]
        if not (self.triggers.events or self.triggers.every_seconds or self.triggers.every_hours):
            problems.append("triggers needs events, every_seconds or every_hours")
        if self.subject == "events" and not self.triggers.events:
            problems.append("an events policy needs triggers.events")
        problems += [f"claims {k!r}: the {self.subject} subject can claim only {sorted(subject.claimable)}" for k in self.claims
                     if k not in subject.claimable]
        problems += [f"claims {k!r} must also be in triggers.events" for k in self.claims if k not in self.triggers.events]
        if not self.questions:
            problems.append("questions is empty")
        for name, q in self.questions.items():
            problems += [f"questions.{name}: {p}" for p in _question_problems(name, q, subject.has_options)]
        problems += self._decide_problems(subject.method is not None)
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def _decide_problems(self, can_act: bool) -> list[str]:
        d, qs, out = self.decide, self.questions, []
        if d.act_with is not None:
            q = qs.get(d.act_with)
            if not can_act:
                out.append(f"the {self.subject} subject cannot act; remove decide.act_with and use escalate_if")
            elif q is None or q.type != "choice":
                out.append(f"decide.act_with must name a choice question, not {d.act_with!r}")
            elif not isinstance(q.criteria, dict) or "escalate" not in q.criteria:
                out.append(f"questions.{d.act_with} must have an 'escalate' label that says when the director must decide")
            if not d.vetoes:
                out.append("a policy that acts needs at least one veto: a noul question that checks directive.never")
        for name in d.vetoes:
            if (q := qs.get(name)) is None or q.type != "noul":
                out.append(f"decide.vetoes.{name} must name a noul question")
        for name in d.escalate_if:
            if (q := qs.get(name)) is None or q.type == "choice":
                out.append(f"decide.escalate_if.{name} must name a noul or score question")
        return out


def _question_problems(name: str, q: QuestionSpec, has_options: bool) -> list[str]:
    out = [] if _NAME.match(name) and name != REPORT_UP else [f"bad question name (lowercase words with _; {REPORT_UP} is reserved)"]
    match q.type:
        case "noul" if q.criteria is not None and (not isinstance(q.criteria, dict) or set(q.criteria) - {"true", "false"}):
            out.append("noul criteria is {true: ..., false: ...}")
        case "choice":
            if q.options_from_subject and not has_options:
                out.append("this subject has no options")
            if not isinstance(q.criteria, dict) and not q.options_from_subject:
                out.append("choice criteria is {label: description}")
            elif not q.options_from_subject and len(q.criteria or {}) < 2:
                out.append("a choice needs at least two labels")
        case "score" if not isinstance(q.criteria, list) or not 2 <= len(q.criteria) <= 10:
            out.append("score criteria is a list of 2 to 10 level descriptions, lowest first")
    if q.options_from_subject and q.type != "choice":
        out.append("options_from_subject is for choice questions")
    return out


def jev_questions(spec: PolicySpec, options: tuple[str, ...], report_up: bool) -> dict[str, Question]:
    """The Jev questions of `spec` about a thing with these options; `report_up` adds the directive's report_when check."""
    out: dict[str, Question] = {}
    for name, q in spec.questions.items():
        match q.type:
            case "noul":
                criteria: dict[str, JsonValue] | None = {**q.criteria} if isinstance(q.criteria, dict) else None
                out[name] = Noul(instructions=q.instructions, criteria=criteria)
            case "score":
                out[name] = Score(instructions=q.instructions, criteria=list(q.criteria or []))
            case "choice":
                labels: dict[str, JsonValue] = {o: None for o in options} if q.options_from_subject else {}
                labels |= q.criteria if isinstance(q.criteria, dict) else {}
                out[name] = Choice(instructions=q.instructions, criteria=labels)
    if report_up:
        out[REPORT_UP] = Noul(instructions="Does this situation match any condition in directive.report_when?",
                              criteria={"true": "It clearly matches at least one listed condition.", "false": "It matches none of them."})
    return out


@dataclass
class Policy:
    name: str
    digest: str
    spec: PolicySpec | None
    error: str | None = None


class PolicyRepository:
    """brain/policies/*.yaml, parsed again when a file's content changes."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.loaded: dict[str, Policy] = {}

    def scan(self) -> dict[str, Policy]:
        files = {p.stem: p for p in sorted(self.directory.glob("*.yaml"))} if self.directory.is_dir() else {}
        for name in set(self.loaded) - set(files):
            del self.loaded[name]
        for name, path in files.items():
            text = path.read_text(encoding="utf-8")
            digest = hashlib.blake2b(text.encode(), digest_size=6).hexdigest()
            if (current := self.loaded.get(name)) is None or current.digest != digest:
                self.loaded[name] = parse(name, text, digest)
        return self.loaded


def parse(name: str, text: str, digest: str = "") -> Policy:
    try:
        data: Any = yaml.safe_load(text)
        return Policy(name, digest, PolicySpec.model_validate(data))
    except yaml.YAMLError as e:
        return Policy(name, digest, None, f"YAML: {e}")
    except ValidationError as e:
        return Policy(name, digest, None, "; ".join(f"{'.'.join(map(str, x['loc'])) or 'policy'}: {x['msg']}" for x in e.errors(include_url=False)))
