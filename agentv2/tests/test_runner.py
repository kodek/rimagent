from __future__ import annotations

import subprocess

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo

from agentv2.runtime import open_runtime
from agentv2.scripted import call, scripted_model
from agentv2.wake import TICKS_PER_HOUR, Wake


class Script:
    def __init__(self) -> None:
        self.responses: list[ModelResponse | Exception] = []
        self.received: list[list[ModelMessage]] = []
        self.on_call = None

    def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.received.append(list(messages))
        if self.on_call:
            self.on_call(len(self.received))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
async def started(settings, bridge, bus):
    script = Script()
    async with open_runtime(settings, bus, bridge, scripted_model(script)) as rt:
        await rt.runner.prepare()
        await rt.runner.ensure_game()
        yield rt, script


async def restarted(settings, bridge, bus, script):
    async with open_runtime(settings, bus, bridge, scripted_model(script)) as rt:
        await rt.runner.prepare()
        await rt.runner.ensure_game()
        return rt


def prompts(messages: list[ModelMessage]) -> str:
    return "\n".join(str(p.content) for m in messages for p in getattr(m, "parts", []) if p.part_kind == "user-prompt")


async def test_resume_then_step_schedules_the_next_wake(started, game):
    rt, script = started
    assert rt.runner.episode.number == 1 and rt.runner.episode.seed == "rimagent-1"
    script.responses = [call("rw_state_summary"), call("end_turn", {"notes": "all calm", "wake_in_hours": 6, "wake_on": ["letter"]})]
    outcome = await rt.runner.step(Wake("scheduled check-in", False))
    assert outcome.notes == "all calm"
    assert rt.runner.wake.next_tick == game.tick + 6 * TICKS_PER_HOUR
    assert rt.runner.wake.wake_on == {"letter"}
    assert "## Wake trigger\nscheduled check-in" in prompts(script.received[0])


async def test_the_conversation_continues_across_steps(started):
    rt, script = started
    script.responses = [call("end_turn", {"notes": "first"}), call("end_turn", {"notes": "second"})]
    await rt.runner.step(Wake("first wake", False))
    await rt.runner.step(Wake("second wake", False))
    assert "first wake" in prompts(script.received[1]) and "second wake" in prompts(script.received[1])
    assert rt.director.notes == ["first", "second"]


async def test_a_failed_step_keeps_its_history(started):
    rt, script = started
    script.responses = [call("rw_state_summary"), ModelHTTPError(500, "scripted")]
    outcome = await rt.runner.step(Wake("the model breaks", False))
    assert outcome.error
    script.responses = [call("end_turn", {"notes": "back"})]
    await rt.runner.step(Wake("next wake", False))
    assert "the model breaks" in prompts(script.received[-1]) and "next wake" in prompts(script.received[-1])


async def test_operator_message_wakes_and_gets_a_reply(started, bus):
    rt, script = started
    await rt.controls.say("build a freezer")
    wake = rt.runner.inbox.take_forced()
    assert wake == Wake("operator message", True)
    script.responses = [call("reply_to_operator", {"text": "on it"}), call("end_turn", {"notes": "freezer planned"})]
    await rt.runner.step(wake)
    assert "build a freezer" in prompts(script.received[0])
    assert rt.runner.inbox.operator == []
    assert any(e["kind"] == "reply" for e in bus.since(0))
    assert "build a freezer" in rt.brain.operator.path.read_text()


async def test_urgent_event_reaches_the_model_mid_step(started, game):
    rt, script = started

    def raid_arrives(n: int) -> None:
        if n == 1:
            game.add_event("colonist_downed", "Bob is down")

    script.on_call = raid_arrives
    script.responses = [call("rw_state_summary"), call("end_turn", {"notes": "handled"})]
    original = rt.bridge.call

    async def call_and_poll(method, params=None, timeout_ms=None):
        result = await original(method, params, timeout_ms)
        if method == "state.summary" and rt.director.active is not None:
            await rt.runner.poller.poll_once(rt.runner.episode)
        return result

    rt.bridge.call = call_and_poll
    await rt.runner.step(Wake("scheduled check-in", False))
    assert "URGENT" in prompts(script.received[1]) and "Bob is down" in prompts(script.received[1])


async def test_end_episode_reflects_scores_commits_and_starts_a_new_game(started, game, root):
    rt, script = started
    script.responses = [call("journal_write_memory", {"content": "raids come early"}), call("finish", {"notes": "lesson written"})]
    await rt.runner.end_episode("test over")
    row = rt.runner.scores.history()[-1]
    assert row["episode"] == 1 and row["ended"] == "test over" and row["notes"] == "lesson written"
    assert rt.runner.episode.number == 2 and game.seed == "rimagent-2"
    log = subprocess.run(["git", "log", "--oneline"], cwd=root, capture_output=True, text=True, check=True).stdout
    assert "episode 1 (rimagent-1): test over" in log
    assert "raids come early" in rt.brain.layout.journal().read_text()


async def test_a_restarted_agent_resumes_the_conversation_and_the_episode(started, settings, bridge, bus, game):
    rt, script = started
    game.add_event("hostile_group", "raiders")
    await rt.runner.poller.poll_once(rt.runner.episode)
    rt.runner.episode.pass_notes.append("[improvement pass day 1] wrote a watcher")
    script.responses = [call("end_turn", {"notes": "remember me"})]
    await rt.runner.step(Wake("before restart", False))
    rt.runner.episodes.save(rt.runner.episode)
    again = await restarted(settings, bridge, bus, script)
    assert again.runner.episode.number == 1 and again.runner.episode.raids == 1
    assert [e["text"] for e in again.runner.episode.timeline] == ["raiders"]
    assert again.runner.episode.pass_notes == ["[improvement pass day 1] wrote a watcher"]
    assert "before restart" in prompts(again.director.history)


async def test_a_failing_reflection_still_ends_the_episode(started):
    rt, script = started
    script.responses = []
    await rt.runner.end_episode("model gone")
    assert rt.runner.scores.history()[-1]["ended"] == "model gone"
    assert rt.runner.episode.number == 2


async def test_an_ended_episode_is_not_resumed(started, settings, bridge, bus, game):
    rt, script = started
    script.responses = [call("finish", {"notes": "x"})]
    rt.runner.episode.ended = True
    rt.runner.episodes.save(rt.runner.episode)
    again = await restarted(settings, bridge, bus, script)
    assert again.runner.episode.number == 2 and game.seed == "rimagent-2"
