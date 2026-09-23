from __future__ import annotations

import pytest
from test_runner import Script, prompts

from agentv2 import situation, world
from agentv2.runtime import open_runtime
from agentv2.scripted import call, code, scripted_model
from agentv2.situation import Snapshot, Wakeup
from agentv2.wake import Wake
from agentv2.world import Tracked, View

SUMMARY = {"day": 3, "hour": 14, "season": "Summer", "weather": "Rain", "temp_outdoor": 21, "colonists": 2, "food_days": 5.5,
           "key_stocks": {"WoodLog": 300, "Steel": 80},
           "colonist_list": [{"name": "Bob", "id": "Human1", "pos": [10, 10], "mood": 60, "health": 100, "job": "Mining",
                              "top_skills": "Mining 8!", "weapon": "Revolver"},
                             {"name": "Ann", "id": "Human2", "pos": [11, 10], "mood": 40, "health": 70, "job": "downed", "bleeding": 0.4}],
           "outside_storage": {"stacks": 9, "rotting": 3, "storage_cells_free": 0}}
BASE = {"rooms": [{"ref": "Room:1", "role": "Bedroom", "size": "5x4 (20 cells)", "free_floor": 8, "doors": [{"leads_to": "outside"}],
                   "contents": {"Bed": 2}, "temp": 3, "problems": ["cold (3C)"]}],
        "trapped_colonists": [{"pawn": "Cid", "at": [40, 40], "note": "cannot reach home"}], "blueprints_pending": 4, "frames_in_progress": 1}


def report(snap: Snapshot, **wake) -> str:
    return situation.render(snap, Wakeup("scheduled check-in", **wake)).text


def test_the_first_report_shows_the_base_and_the_problems():
    text = report(Snapshot(SUMMARY, BASE))
    assert "## The base" in text and "Room:1 Bedroom 5x4 (20 cells), free floor 8, doors to outside, 3C [Bed x2]" in text
    assert "- Room:1 Bedroom: cold (3C)" in text and "TRAPPED: Cid at [40, 40]" in text and "rotting 3" in text
    assert "Mining 8!; weapon Revolver" in text and "DOWNED bleeding 0.4" in text
    assert "## Since your last step" not in text


def test_a_later_report_shows_what_changed_instead_of_the_base():
    before = View.of({**SUMMARY, "day": 2, "hour": 20, "key_stocks": {"WoodLog": 500, "Steel": 80},
                      "colonist_list": [{"name": "Bob", "mood": 75, "health": 100}, {"name": "Ann", "mood": 45, "health": 100}]},
                     {**BASE, "rooms": [{**BASE["rooms"][0], "contents": {"Bed": 1}, "problems": ["cold (3C)", "dark"]}]})
    text = report(Snapshot(SUMMARY, BASE), previous=before, show_base=False)
    assert "## The base" not in text
    changes = text.split("## Since your last step (day 2 20h)\n")[1].split("\n\n")[0]
    for line in ("Ann: ok -> downed", "Bob mood 75 -> 60", "Ann health 100 -> 70", "Room:1 Bedroom: Bed 1 -> 2; fixed: dark", "WoodLog 500 -> 300",
                 "blueprints 4 and frames 1 did not change: is anybody building?", "TRAPPED: Cid"):
        assert f"- {line}" in changes


def test_threats_come_from_state_threats():
    threats = {"threat_points": 350, "hostiles": [{"name": "Raider A", "faction": "Pirates", "weapon": "Rifle", "dist_home": 42, "health": 100},
                                                  {"def": "Warg", "mental": "Manhunter", "dist_home": 12}]}
    text = report(Snapshot(SUMMARY, BASE, threats=threats))
    assert "## THREATS: 2 hostile (threat points 350)" in text
    assert "- Raider A: Pirates, weapon Rifle, 42 cells from home, health 100" in text and "- Warg: 12 cells from home, Manhunter" in text


def test_tracked_values_keep_their_history_and_show_a_trend():
    tracked = {"food": Tracked(path="food_days"), "rooms": Tracked(path="rooms.#", method="state.base")}
    for food in (7.0, 7.0, 5.5):
        tracked["food"].record(food)
    tracked["rooms"].record(1.0)
    text = report(Snapshot(SUMMARY, BASE), tracked=tracked)
    assert "- food: 7 -> 5.5 down" in text and "- rooms: 1" in text
    assert situation.render(Snapshot(SUMMARY, BASE), Wakeup("x", tracked=tracked)).changes == "food 5.5 (-1.5), rooms 1"
    assert world.dig({"a": [{"b": 2}]}, "a.0.b") == 2 and world.dig({"a": [1, 2]}, "a.#") == 2 and world.dig({"a": 1}, "a.b") is None


async def test_sample_reads_each_method_once(bridge, game):
    tracked = world.default_tracked() | {"rooms": Tracked(path="rooms.#", method="state.base"), "rooms2": Tracked(path="home_center.0", method="state.base"),
                                         "bad": Tracked(path="x", method="no.such")}
    game.calls.clear()
    await world.sample(bridge, tracked, await bridge.call("state.summary"))
    assert [m for m, _ in game.calls].count("state.base") == 1
    assert tracked["wood"].history == [240.0] and tracked["rooms"].history == [1.0] and tracked["rooms2"].history == [120.0]
    assert str(tracked["bad"].history[0]).startswith("error: unknown method")


@pytest.fixture
async def runtime(settings, bridge, bus):
    script = Script()
    async with open_runtime(settings, bus, bridge, scripted_model(script)) as rt:
        await rt.runner.prepare()
        await rt.runner.ensure_game()
        yield rt, script


async def test_the_director_sees_changes_and_its_own_tracked_values(runtime, game):
    rt, script = runtime
    script.responses = [code("await track_value(label='steel', path='key_stocks.Steel')"),
                        code("await track_value(label='x', path='done', method='ui.draft')"), call("end_turn", {"notes": "tracking"})]
    await rt.runner.step(Wake("first", False))
    first = prompts(script.received[0])
    assert "## The base" in first and "## Since your last step" not in first
    assert "not a read-only method" in str(script.received[-1][-1])
    game.stocks["WoodLog"], game.stocks["Steel"] = 100, 150
    game.rooms[0]["problems"] = ["dark"]
    game.hostiles = [{"id": "Human9", "name": "Raider", "faction": "Pirates", "weapon": "Club", "dist_home": 30, "pos": [1, 1]}]
    script.responses = [call("end_turn", {"notes": "seen"})]
    await rt.runner.step(Wake("second", False))
    second = prompts(script.received[-1]).split("## Wake trigger\nsecond")[1]
    assert "## The base" not in second and "- WoodLog 240 -> 100" in second and "NEW PROBLEM: dark" in second
    assert "- steel: 180 -> 150 down" in second and "- Raider: Pirates, weapon Club, 30 cells from home" in second
    assert rt.runner.episodes.load().tracked["steel"].history == [180.0, 150.0]  # type: ignore[union-attr]
