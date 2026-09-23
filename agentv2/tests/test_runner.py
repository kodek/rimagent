from __future__ import annotations

import subprocess

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo

from agentv2.runner import TICKS_PER_HOUR, Controls, Runner, Wake
from agentv2.scripted import call, scripted_model


class Script:
    def __init__(self) -> None:
        self.responses: list[ModelResponse] = []
        self.received: list[list[ModelMessage]] = []
        self.on_call = None

    def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.received.append(list(messages))
        if self.on_call:
            self.on_call(len(self.received))
        return self.responses.pop(0)


@pytest.fixture
async def started(settings, bridge, bus):
    script = Script()
    runner = Runner(settings, bus, bridge, scripted_model(script))
    async with runner.watchers:
        await runner.prepare()
        await runner.ensure_game()
        yield runner, script


def prompts(messages: list[ModelMessage]) -> str:
    return "\n".join(str(p.content) for m in messages for p in getattr(m, "parts", []) if p.part_kind == "user-prompt")


async def test_resume_then_step_schedules_the_next_wake(started, game):
    runner, script = started
    assert runner.episode.number == 1 and runner.episode.seed == "rimagent-1"
    script.responses = [call("rw_state_summary"), call("end_turn", {"notes": "all calm", "wake_in_hours": 6, "wake_on": ["letter"]})]
    outcome = await runner.step(Wake("scheduled check-in", False))
    assert outcome.notes == "all calm"
    assert runner.next_wake_tick == game.tick + 6 * TICKS_PER_HOUR
    assert runner.turn_wake_on == {"letter"}
    assert "## Wake trigger\nscheduled check-in" in prompts(script.received[0])


async def test_the_conversation_continues_across_steps(started):
    runner, script = started
    script.responses = [call("end_turn", {"notes": "first"}), call("end_turn", {"notes": "second"})]
    await runner.step(Wake("first wake", False))
    await runner.step(Wake("second wake", False))
    assert "first wake" in prompts(script.received[1]) and "second wake" in prompts(script.received[1])


async def test_operator_message_wakes_and_gets_a_reply(started, bus):
    runner, script = started
    await Controls(runner).say("build a freezer")
    wake = await runner.wake_trigger(0)
    assert wake == Wake("operator message", True)
    script.responses = [call("reply_to_operator", {"text": "on it"}), call("end_turn", {"notes": "freezer planned"})]
    await runner.step(wake)
    assert "build a freezer" in prompts(script.received[0])
    assert runner.operator_queue == []
    assert any(e["kind"] == "reply" for e in bus.since(0))
    assert "build a freezer" in runner.brain.operator.path.read_text()


async def test_urgent_event_reaches_the_model_mid_step(started, game):
    runner, script = started

    def raid_arrives(n: int) -> None:
        if n == 1:
            game.add_event("colonist_downed", "Bob is down")

    script.on_call = raid_arrives
    script.responses = [call("rw_state_summary"), call("end_turn", {"notes": "handled"})]
    original = runner.bridge.call

    async def call_and_poll(method, params=None, timeout_ms=None):
        result = await original(method, params, timeout_ms)
        if method == "state.summary" and runner.thinking:
            await runner.poll_once()
        return result

    runner.bridge.call = call_and_poll
    await runner.step(Wake("scheduled check-in", False))
    assert "URGENT" in prompts(script.received[1]) and "Bob is down" in prompts(script.received[1])


async def test_end_episode_reflects_scores_commits_and_starts_a_new_game(started, game, root):
    runner, script = started
    script.responses = [call("journal_write_memory", {"content": "raids come early"}), call("finish", {"notes": "lesson written"})]
    await runner.end_episode("test over")
    row = runner.scores.history()[-1]
    assert row["episode"] == 1 and row["ended"] == "test over" and row["notes"] == "lesson written"
    assert runner.episode.number == 2 and game.seed == "rimagent-2"
    log = subprocess.run(["git", "log", "--oneline"], cwd=root, capture_output=True, text=True).stdout
    assert "episode 1 (rimagent-1): test over" in log
    assert "raids come early" in runner.brain.layout.journal().read_text()


async def test_a_restarted_agent_resumes_the_conversation_and_the_episode(started, settings, bridge, bus, game):
    runner, script = started
    game.add_event("hostile_group", "raiders")
    await runner.poll_once()
    runner.episode.pass_notes.append("[improvement pass day 1] wrote a watcher")
    script.responses = [call("end_turn", {"notes": "remember me"})]
    await runner.step(Wake("before restart", False))
    runner.episodes.save(runner.episode)
    again = Runner(settings, bus, bridge, scripted_model(script))
    async with again.watchers:
        await again.prepare()
        await again.ensure_game()
    assert again.episode.number == 1 and again.episode.raids == 1
    assert [e["text"] for e in again.episode.timeline] == ["raiders"]
    assert again.episode.pass_notes == ["[improvement pass day 1] wrote a watcher"]
    assert "before restart" in prompts(again.history)


async def test_a_failing_reflection_still_ends_the_episode(started, game):
    runner, script = started
    script.responses = []
    await runner.end_episode("model gone")
    assert runner.scores.history()[-1]["ended"] == "model gone"
    assert runner.episode.number == 2


async def test_an_ended_episode_is_not_resumed(started, settings, bridge, bus, game):
    runner, script = started
    script.responses = [call("finish", {"notes": "x"})]
    runner.episode.ended = True
    runner.episodes.save(runner.episode)
    again = Runner(settings, bus, bridge, scripted_model(script))
    async with again.watchers:
        await again.prepare()
        await again.ensure_game()
    assert again.episode.number == 2 and game.seed == "rimagent-2"


async def test_a_broken_authored_capability_is_left_out(started, bus):
    runner, script = started
    runner.brain.creation.store.write("broken", "from dataclasses import dataclass\nfrom pydantic_ai.capabilities import AbstractCapability\n"
                                               "from pydantic_ai.exceptions import UserError\n@dataclass\nclass Broken(AbstractCapability):\n"
                                               "    async def before_run(self, ctx):\n        raise UserError('broken on purpose')\n")
    script.responses = [call("end_turn", {"notes": "played anyway"})]
    outcome = await runner.step(Wake("x", False))
    assert outcome.notes == "played anyway"
    assert any("authored capability broke" in e["data"].get("text", "") for e in bus.since(0, kinds={"error"}))
