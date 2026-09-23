from __future__ import annotations

import asyncio
import subprocess

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo

from agentv2.bridge import BridgeError
from agentv2.episode import Episode
from agentv2.events import ToolCall
from agentv2.roles import IMPROVER
from agentv2.runtime import open_runtime
from agentv2.scripted import call, code, scripted_model
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
    script.responses = [code("await rw_state_summary()"), call("end_turn", {"notes": "all calm", "wake_in_hours": 6, "wake_on": ["letter"]})]
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
    assert await rt.director.notes(rt.runner.episode.colony) == ["first", "second"]


async def test_a_failed_step_keeps_its_history(started):
    rt, script = started
    script.responses = [code("await rw_state_summary()"), ModelHTTPError(500, "scripted")]
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
    script.responses = [code("await reply_to_operator(text='on it')"), call("end_turn", {"notes": "freezer planned"})]
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
    script.responses = [code("await rw_state_summary()"), call("end_turn", {"notes": "handled"})]
    original = rt.bridge.call

    async def call_and_poll(method, params=None, timeout_ms=None):
        result = await original(method, params, timeout_ms)
        if method == "state.summary" and rt.director.active is not None:
            await rt.runner.poller.poll_once(rt.runner.episode)
        return result

    rt.bridge.call = call_and_poll
    await rt.runner.step(Wake("scheduled check-in", False))
    assert "URGENT" in prompts(script.received[1]) and "Bob is down" in prompts(script.received[1])


async def test_the_operator_ends_the_episode_mid_step(started):
    rt, script = started
    gate = asyncio.Event()
    script.responses = [code("await rw_state_summary()")] * 3
    original = rt.bridge.call

    async def slow_summary(method, params=None, timeout_ms=None):
        if method == "state.summary" and rt.director.active is not None:
            gate.set()
            await asyncio.sleep(0.3)
        return await original(method, params, timeout_ms)

    rt.bridge.call = slow_summary
    step = asyncio.create_task(rt.runner.step(Wake("long step", False)))
    await gate.wait()
    await rt.controls.end_episode()
    outcome = await step
    assert outcome.error and "RunCancelled" in outcome.error
    assert rt.runner.inbox.end == "the operator ended the episode"
    rt.bridge.call = original
    script.responses = [call("end_turn", {"notes": "after the cancel"})]
    assert (await rt.runner.step(Wake("next step", False))).notes == "after the cancel"
    assert "long step" in prompts(script.received[-1]) and "next step" in prompts(script.received[-1])


async def test_end_episode_reflects_scores_commits_and_starts_a_new_game(started, game, root):
    rt, script = started
    script.responses = [code("await journal_write_memory(content='raids come early')"), call("finish", {"notes": "lesson written"})]
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
    assert "before restart" in prompts(await again.director.history(again.runner.episode.colony))


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


async def test_a_crashed_game_continues_from_its_save(started, game):
    rt, _ = started
    checkpoint = rt.runner.episode.checkpoint
    assert checkpoint is not None and "agentv2-autosave" in game.saves
    game.advance(30)
    game.add_event("colonist_died", "Bob died")
    await rt.runner.poller.poll_once(rt.runner.episode)
    assert rt.runner.episode.deaths == 1
    game.crash()
    with pytest.raises(BridgeError):
        await rt.runner.ensure_game()
    game.alive = True
    game.calls.clear()
    await rt.runner.ensure_game()
    episode = rt.runner.episode
    assert game.state == "playing" and game.tick == checkpoint.tick
    assert episode.number == 1 and episode.deaths == 0 and episode.timeline[-1]["kind"] == "reloaded"
    assert rt.runner.poller.last_seq == len(game.ledger)
    assert ("game.load", {"name": "agentv2-autosave"}) in game.calls and "steward.enable" in [m for m, _ in game.calls]
    wake = rt.runner.inbox.take_forced()
    assert wake is not None and f"save of day {checkpoint.day}" in wake.trigger


async def test_the_main_menu_does_not_end_an_episode_that_has_a_save(started, game):
    rt, _ = started
    game.state = "menu"
    await rt.runner.play_episode()
    assert rt.runner.scores.history() == [] and rt.runner.episode.unfinished


async def test_a_save_that_does_not_load_ends_the_episode(started, game):
    rt, script = started
    game.state = "menu"
    original = rt.bridge.call

    async def broken_load(method, params=None, timeout_ms=None):
        if method == "game.load":
            raise BridgeError("the save is corrupt")
        return await original(method, params, timeout_ms)

    rt.bridge.call = broken_load
    script.responses = [call("finish", {"notes": "crash noted"})]
    await rt.runner.ensure_game()
    assert rt.runner.scores.history()[-1]["ended"] == "the game crashed and its save did not load"
    assert rt.runner.episode.number == 2 and game.seed == "rimagent-2"


async def test_an_abandoned_episode_number_is_not_used_again(settings, bridge, bus, game):
    game.state = "menu"
    async with open_runtime(settings, bus, bridge, scripted_model(Script())) as rt:
        rt.runner.episodes.save(Episode(number=3, seed="rimagent-3"))
        await rt.runner.prepare()
        await rt.runner.ensure_game()
        assert rt.runner.episode.number == 4 and game.seed == "rimagent-4"


async def test_the_runner_restarts_a_silent_game(started, game, settings, tmp_path):
    rt, _ = started
    marker = tmp_path / "restarted"
    settings.play.restart_command = ["touch", str(marker)]
    settings.play.restart_after_s = 0
    game.alive = False

    async def game_comes_back() -> None:
        while not marker.exists():
            await asyncio.sleep(0.05)
        game.alive = True

    back = asyncio.create_task(game_comes_back())
    await asyncio.wait_for(rt.runner.recover(), 10)
    await back
    assert marker.exists()


async def test_operator_order_switches_and_the_research_queue_last_into_a_new_game(settings, bridge, bus, game):
    settings.steward.orders_off = ["corpses"]
    settings.steward.research_queue = ["Batteries"]
    script = Script()
    rt = await restarted(settings, bridge, bus, script)
    await rt.controls.set_order("beds", False)
    wake = rt.runner.inbox.take_forced()
    assert wake is not None and "standing order beds" in wake.trigger
    game.calls.clear()
    await rt.runner.new_game()
    orders = [p for m, p in game.calls if m == "steward.orders.set"]
    assert orders == [{"id": "all", "enabled": True}, {"id": "beds", "enabled": False}, {"id": "corpses", "enabled": False}]
    assert ("steward.research", {"queue": ["Batteries"]}) in game.calls
    await rt.controls.set_order("all", False)
    game.calls.clear()
    await rt.runner.game.apply_steward()
    assert [p for m, p in game.calls if m == "steward.orders.set"] == [{"id": "all", "enabled": False}]


async def test_a_failed_step_is_tried_again_after_an_hour(started, game):
    rt, script = started
    script.responses = [ModelHTTPError(503, "down")]
    outcome = await rt.runner.step(Wake("event: hostile_group: raiders", True))
    assert outcome.error and rt.runner.wake.next_tick == game.tick + TICKS_PER_HOUR
    assert rt.runner.wake.check(game.tick + TICKS_PER_HOUR, [], [], None) == Wake("again after a failed step: event: hostile_group: raiders", True)


def reminders(messages: list[ModelMessage]) -> list[str]:
    return [str(p.content) for m in messages for p in getattr(m, "parts", []) if "<system-reminder>" in str(getattr(p, "content", ""))]


async def test_the_director_is_reminded_of_matching_skills_until_it_loads_them(started):
    rt, script = started
    script.responses = [call("load_capability", {"id": "defense-basics"}), call("end_turn", {"notes": "ready"})]
    await rt.runner.step(Wake("event: hostile_group: A pirate band approaches", True))
    assert "not loaded: defense-basics" in reminders(script.received[0])[0]
    assert reminders(script.received[1]) == []
    history = await rt.director.history(rt.runner.episode.colony)
    assert reminders(history) == []
    script.responses = [call("end_turn", {"notes": "still ready"})]
    await rt.runner.step(Wake("event: hostile_group: more raiders", True))
    assert reminders(script.received[-1]) == []


async def test_the_improver_sees_the_call_patterns_that_repeat(started, bus):
    rt, _ = started
    for snippet, names in enumerate([["rw_map_find", "rw_map_find", "rw_ui_designate"]] * 3 + [["rw_state_summary"]] * 4):
        for n, name in enumerate(names):
            bus.emit(ToolCall(name=name, args={}, id=f"c{snippet}-{n}", parent=f"run{snippet}"), stream="play")
    stats = rt.runner.passes.usage_stats()
    assert "- rw_map_find > rw_ui_designate  x3" in stats and "rw_state_summary  x" not in stats
    assert "- rw_map_find: 6" in stats


async def test_scratch_files_last_for_the_game_and_the_passes_only_read_them(started, settings):
    rt, script = started
    script.responses = [code("import json, pathlib\npathlib.Path('/scratch/beds.json').write_text(json.dumps([1, 2]))"), call("end_turn", {"notes": "x"})]
    await rt.runner.step(Wake("first", False))
    script.responses = [code("import json, pathlib\njson.loads(pathlib.Path('/scratch/beds.json').read_text())"), call("end_turn", {"notes": "x"})]
    await rt.runner.step(Wake("second", False))
    assert "[1,2]" in str(script.received[-1][-1].parts).replace(" ", "")
    script.responses = [code("import pathlib\npathlib.Path('/scratch/pass.txt').write_text('x')"), call("finish", {"notes": "tried"})]
    await rt.agents.improver.run("improve", deps=rt.runner.deps(IMPROVER))
    assert not (settings.scratch / "pass.txt").exists() and (settings.scratch / "beds.json").exists()
    await rt.runner.new_game()
    assert list(settings.scratch.iterdir()) == []
