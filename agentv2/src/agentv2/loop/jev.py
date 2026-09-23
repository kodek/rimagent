"""Jev, TypeSafe's System One model: named yes/no (noul), choice and score questions about one state, all answered with
probabilities in one request. It writes no text and cannot count or do math, so the loop gives it computed features.

The client keeps the fast loop fast and bounded: a short timeout, one hedged request for a slow answer, a request rate
limit, a spend limit per hour, and a circuit breaker. When it is unavailable it says so at once instead of waiting."""
from __future__ import annotations

import asyncio
import collections
import time
from collections.abc import Callable
from typing import Annotated, Any, Literal, Protocol

import httpx
from pydantic import BaseModel, Field, JsonValue, TypeAdapter, ValidationError

from ..config import JevSettings

SPECIAL = ("escalate", "none")


class Noul(BaseModel):
    type: Literal["noul"] = "noul"
    instructions: JsonValue = None
    criteria: dict[str, JsonValue] | None = None


class Choice(BaseModel):
    type: Literal["choice"] = "choice"
    instructions: JsonValue = None
    criteria: dict[str, JsonValue] = Field(min_length=2, max_length=255)


class Score(BaseModel):
    type: Literal["score"] = "score"
    instructions: JsonValue = None
    criteria: list[JsonValue] = Field(min_length=2, max_length=10)


Question = Annotated[Noul | Choice | Score, Field(discriminator="type")]


class NoulAnswer(BaseModel):
    type: Literal["noul"]
    noul: float


class ChoiceAnswer(BaseModel):
    type: Literal["choice"]
    choice: str
    confidence: float
    probabilities: dict[str, float]


class ScoreAnswer(BaseModel):
    type: Literal["score"]
    score: float
    confidence: float
    probabilities: dict[str, float] = Field(default_factory=dict)


Answer = Annotated[NoulAnswer | ChoiceAnswer | ScoreAnswer, Field(discriminator="type")]


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float | None = None


class Reply(BaseModel):
    model: str
    answers: dict[str, Answer]
    usage: Usage = Field(default_factory=Usage)


_QUESTIONS = TypeAdapter(dict[str, Question])


class JevError(Exception):
    """A request failed."""


class JevUnavailable(JevError):
    """The client refuses to send now: circuit open, rate limit or spend limit. Try again later."""


class Health(BaseModel):
    available: bool
    reason: str | None = None
    calls_last_minute: int = 0
    usd_last_hour: float = 0.0
    failures: int = 0
    last_ms: float | None = None


class Jev(Protocol):
    async def ask(self, state: JsonValue, questions: dict[str, Question]) -> Reply: ...

    def health(self) -> Health: ...


def check_reply(reply: Reply, questions: dict[str, Question]) -> Reply:
    for name, question in questions.items():
        answer = reply.answers.get(name)
        if answer is None or answer.type != question.type:
            raise JevError(f"Jev gave no {question.type} answer for {name!r}")
    return reply


class JevClient:
    def __init__(self, settings: JevSettings, transport: httpx.AsyncBaseTransport | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.settings = settings
        self._clock = clock
        self._client = httpx.AsyncClient(base_url=settings.base_url.rstrip("/"), transport=transport, timeout=settings.timeout_s,
                                         headers={"Authorization": f"Bearer {settings.api_key}"})
        self._slots = asyncio.Semaphore(settings.max_concurrency)
        self._calls: collections.deque[float] = collections.deque()
        self._spend: collections.deque[tuple[float, float]] = collections.deque()
        self._failures = 0
        self._open_until = 0.0
        self._last_ms: float | None = None

    async def aclose(self) -> None:
        await self._client.aclose()

    def health(self) -> Health:
        now = self._clock()
        self._trim(now)
        spent = sum(usd for _, usd in self._spend)
        reason = None
        if now < self._open_until:
            reason = f"circuit open after {self._failures} failed requests"
        elif spent >= self.settings.usd_per_hour:
            reason = f"spend limit: ${spent:.2f} in the last hour"
        elif len(self._calls) >= self.settings.requests_per_minute:
            reason = f"rate limit: {len(self._calls)} requests in the last minute"
        return Health(available=reason is None, reason=reason, calls_last_minute=len(self._calls), usd_last_hour=round(spent, 4),
                      failures=self._failures, last_ms=self._last_ms)

    async def ask(self, state: JsonValue, questions: dict[str, Question]) -> Reply:
        health = self.health()
        if not health.available:
            raise JevUnavailable(health.reason)
        body = {"model": self.settings.model, "state": state,
                "questions": _QUESTIONS.dump_python(questions, mode="json", exclude_none=True)}
        started = self._clock()
        tasks = {asyncio.create_task(self._attempt(body))}
        try:
            done, _ = await asyncio.wait(tasks, timeout=self.settings.hedge_after_s)
            if not done:
                tasks.add(asyncio.create_task(self._attempt(body)))
            reply = await _first_success(tasks)
        except JevError:
            self._failed()
            raise
        finally:
            for task in tasks:
                task.cancel()
        self._failures = 0
        self._last_ms = round((self._clock() - started) * 1000, 1)
        usd = reply.usage.cost if reply.usage.cost is not None else reply.usage.input_tokens * self.settings.usd_per_million_input_tokens / 1e6
        self._spend.append((self._clock(), usd))
        return check_reply(reply, questions)

    async def _attempt(self, body: dict[str, Any]) -> Reply:
        async with self._slots:
            self._calls.append(self._clock())
            try:
                response = await self._client.post("/v1/systemone", json=body)
            except httpx.HTTPError as e:
                raise JevError(f"{type(e).__name__}: {e}") from e
        if response.status_code >= 400:
            raise JevError(f"HTTP {response.status_code}: {response.text[:300]}")
        try:
            return Reply.model_validate_json(response.content)
        except ValidationError as e:
            raise JevError(f"bad Jev reply: {e.errors(include_url=False)[:2]}") from e

    def _failed(self) -> None:
        self._failures += 1
        if self._failures >= self.settings.circuit_failures:
            self._open_until = self._clock() + self.settings.circuit_cooldown_s

    def _trim(self, now: float) -> None:
        while self._calls and now - self._calls[0] > 60:
            self._calls.popleft()
        while self._spend and now - self._spend[0][0] > 3600:
            self._spend.popleft()


async def _first_success(tasks: set[asyncio.Task[Reply]]) -> Reply:
    pending, errors = set(tasks), []
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if (error := task.exception()) is None:
                return task.result()
            errors.append(error)
    raise errors[0] if isinstance(errors[0], JevError) else JevError(str(errors[0]))
