"""A stand-in for Jev, for tests and for `agentv2 fake`. By default it leans to the first ordinary label of each choice,
says no to each yes/no question, and gives each score its lowest level. A responder can script any answer."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import JsonValue

from .jev import SPECIAL, Choice, Health, JevUnavailable, Noul, Question, Reply, Score, check_reply

Responder = Callable[[JsonValue, dict[str, Question]], dict[str, Any]]


def lean(question: Question, label: str | None = None, p: float = 0.8) -> dict[str, Any]:
    """The answer that puts probability `p` on `label` (a choice), on yes (a noul) or on that level (a score)."""
    match question:
        case Noul():
            return {"type": "noul", "noul": p}
        case Choice(criteria=criteria):
            labels = list(criteria)
            pick = label if label is not None else next((x for x in labels if x not in SPECIAL), labels[0])
            rest = (1 - p) / max(1, len(labels) - 1)
            probabilities = {x: p if x == pick else rest for x in labels}
            n = len(labels)
            return {"type": "choice", "choice": pick, "probabilities": probabilities, "confidence": round((n * p - 1) / (n - 1), 3)}
        case Score(criteria=criteria):
            level = int(label or 0)
            rest = (1 - p) / max(1, len(criteria) - 1)
            return {"type": "score", "score": float(level), "confidence": p,
                    "probabilities": {str(i): p if i == level else rest for i in range(len(criteria))}}


def default_answer(question: Question) -> dict[str, Any]:
    return lean(question, p=0.1) if isinstance(question, Noul) else lean(question)


@dataclass
class FakeJev:
    respond: Responder | None = None
    available: bool = True
    calls: list[tuple[JsonValue, dict[str, Question]]] = field(default_factory=list)

    async def ask(self, state: JsonValue, questions: dict[str, Question]) -> Reply:
        if not self.available:
            raise JevUnavailable("the fake Jev is switched off")
        self.calls.append((state, questions))
        scripted = self.respond(state, questions) if self.respond else {}
        answers = {name: scripted.get(name) or default_answer(q) for name, q in questions.items()}
        tokens = sum(len(str(x)) for x in (state, questions)) // 4
        return check_reply(Reply.model_validate({"model": "fake-jev", "answers": answers, "usage": {"input_tokens": tokens}}), questions)

    def health(self) -> Health:
        return Health(available=self.available, reason=None if self.available else "the fake Jev is switched off",
                      calls_last_minute=len(self.calls))
