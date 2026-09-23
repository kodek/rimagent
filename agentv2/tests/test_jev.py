from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest

from agentv2.config import JevSettings
from agentv2.loop.fakejev import FakeJev, lean
from agentv2.loop.jev import Choice, JevClient, JevError, JevUnavailable, Noul, Score

QUESTIONS = {
    "reply": Choice(instructions="Which reply?", criteria={"Accept": None, "Reject": None, "escalate": "Ask the director."}),
    "risky": Noul(instructions="Is it risky?", criteria={"true": "yes", "false": "no"}),
    "urgency": Score(instructions="How urgent?", criteria=["later", "today", "now"]),
}
ANSWERS = {
    "reply": {"type": "choice", "choice": "Accept", "confidence": 0.81, "probabilities": {"Accept": 0.88, "Reject": 0.1, "escalate": 0.02}},
    "risky": {"type": "noul", "noul": 0.12},
    "urgency": {"type": "score", "score": 1.05, "confidence": 0.9, "legend": {"0": "later"}, "probabilities": {"0": 0.0, "1": 0.95, "2": 0.05}},
}


def settings(**over) -> JevSettings:
    return JevSettings(**({"api_key": "k", "hedge_after_s": 5} | over))


def reply(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"model": "jev-1.13.0", "answers": ANSWERS, "usage": {"input_tokens": 1_000_000, "output_tokens": 30}})


async def test_the_request_and_the_answers_follow_the_api():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return reply(request)

    client = JevClient(settings(), httpx.MockTransport(handler))
    out = await client.ask({"letter": {"label": "Trade"}}, QUESTIONS)
    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/v1/systemone" and seen[0].headers["authorization"] == "Bearer k"
    assert body["model"] == "jev-1.13.0" and body["state"] == {"letter": {"label": "Trade"}}
    assert body["questions"]["reply"] == {"type": "choice", "instructions": "Which reply?", "criteria": {"Accept": None, "Reject": None,
                                                                                                      "escalate": "Ask the director."}}
    assert body["questions"]["urgency"]["criteria"] == ["later", "today", "now"]
    assert out.answers["reply"].choice == "Accept" and out.answers["risky"].noul == 0.12 and out.answers["urgency"].score == 1.05
    assert client.health().usd_last_hour == 0.042


async def test_a_slow_answer_is_hedged():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            await asyncio.sleep(1)
        return reply(request)

    client = JevClient(settings(hedge_after_s=0.05), httpx.MockTransport(handler))
    started = time.monotonic()
    await client.ask({}, QUESTIONS)
    assert calls == 2 and time.monotonic() - started < 0.5


async def test_failures_open_the_circuit_and_it_closes_after_the_cooldown():
    now = [0.0]
    client = JevClient(settings(circuit_failures=2, circuit_cooldown_s=30), httpx.MockTransport(lambda r: httpx.Response(529, text="overloaded")),
                       clock=lambda: now[0])
    for _ in range(2):
        with pytest.raises(JevError, match="HTTP 529"):
            await client.ask({}, QUESTIONS)
    with pytest.raises(JevUnavailable, match="circuit open"):
        await client.ask({}, QUESTIONS)
    now[0] = 31
    assert client.health().available


async def test_a_missing_answer_and_the_spend_limit():
    def partial(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "m", "answers": {"reply": ANSWERS["reply"]}, "usage": {"input_tokens": 10}})

    with pytest.raises(JevError, match="no noul answer for 'risky'"):
        await JevClient(settings(), httpx.MockTransport(partial)).ask({}, QUESTIONS)
    client = JevClient(settings(usd_per_hour=0.05), httpx.MockTransport(reply))
    await client.ask({}, QUESTIONS)
    await client.ask({}, QUESTIONS)
    with pytest.raises(JevUnavailable, match="spend limit"):
        await client.ask({}, QUESTIONS)


async def test_the_fake_leans_to_the_first_ordinary_label_and_can_be_scripted():
    fake = FakeJev()
    out = await fake.ask({}, QUESTIONS)
    assert out.answers["reply"].choice == "Accept" and out.answers["risky"].noul == 0.1 and out.answers["urgency"].score == 0
    fake.respond = lambda state, qs: {"reply": lean(qs["reply"], "escalate", 0.9)}
    assert (await fake.ask({}, QUESTIONS)).answers["reply"].choice == "escalate"
    fake.available = False
    with pytest.raises(JevUnavailable):
        await fake.ask({}, QUESTIONS)
