from __future__ import annotations

import json

import pytest

from agentv2.brain import Brain, BrainLayout
from agentv2.bus import Bus, JsonlLog
from agentv2.episode import Episode, EpisodeStore
from agentv2.events import Delta, Status
from agentv2.history import Scores, score


@pytest.fixture
def brain(settings) -> Brain:
    return Brain(BrainLayout(settings.brain))


def test_seed_brain_is_valid(brain):
    assert brain.problems() == {}
    assert brain.skills.capability() is not None and not brain.has_authored()
    assert {s.name for s in brain.skills.infos()} >= {"defense-basics", "early-game-food", "work-priorities"}
    assert brain.layout.doctrine.read_text().startswith("# Doctrine")


def test_a_bad_skill_is_reported_and_the_others_still_load(brain):
    bad = brain.layout.skills_dir / "broken"
    bad.mkdir()
    (bad / "SKILL.md").write_text("no frontmatter here\n", encoding="utf-8")
    assert list(brain.problems()) == ["skill broken"]
    skills = brain.skills.capability()
    assert skills is not None and "broken" not in (skills.include or set())


def test_authored_capability_round_trip(brain):
    code = ("from dataclasses import dataclass\nfrom pydantic_ai.capabilities import AbstractCapability\n"
            "@dataclass\nclass Hello(AbstractCapability):\n    def get_instructions(self):\n        return 'hello'\n")
    record = brain.creation.store.write("hello", code)
    assert record.last_error is None
    assert brain.has_authored()
    assert brain.authored()[0]["name"] == "hello"


def test_layout_refuses_names_outside_the_brain(brain):
    for name in ("../AGENTS", "a/b", ".hidden", ""):
        with pytest.raises(ValueError):
            brain.layout.skill(name)
    assert BrainLayout.kind_of("skills/x/SKILL.md") == "skill" and BrainLayout.kind_of("AGENTS.md") == "doctrine"


def test_scores(settings):
    scores = Scores(settings.brain / "scores.jsonl")
    scores.record({"episode": 1, "seed": "s", "score": score(10, 3, 0, 15_000, 60, 4, 1)})
    assert scores.history()[0]["score"] == 100 + 180 + 2.5 + 30 + 32 + 40
    assert "episode | seed" in scores.text()


def test_episode_store_reads_the_old_file_format(tmp_path):
    path = tmp_path / "episode.json"
    path.write_text('{"episode": 3, "seed": "s", "start_day": 2, "deaths": 1, "raids": 0, "last_improve_day": 4, "ended": false}')
    episode = EpisodeStore(path).load()
    assert episode is not None and episode == Episode(number=3, seed="s", start_day=2, deaths=1, last_improve_day=4)
    episode.tally([{"kind": "hostile_group", "text": "raid"}, {"kind": "message", "text": "noise"}])
    EpisodeStore(path).save(episode)
    again = EpisodeStore(path).load()
    assert again is not None and again.raids == 1 and [e["kind"] for e in again.timeline] == ["hostile_group"]


def test_bus_keeps_persistent_events_and_streams_ephemeral_ones(tmp_path):
    log = JsonlLog(tmp_path / "events.jsonl")
    bus = Bus(sinks=[log])
    queue = bus.subscribe()
    bus.emit(Status.model_validate({"day": 3, "phase": "playing"}))
    bus.emit(Delta(part="thinking", text="thinking…"), stream="play")
    bus.emit(Status(deaths=1))
    log.close()
    assert [e["kind"] for e in bus.since(0)] == ["status", "status"]
    assert bus.state == {"phase": "playing", "day": 3, "deaths": 1}
    assert [queue.get_nowait()["data"] for _ in range(3)][1] == {"stream": "play", "part": "thinking", "text": "thinking…"}
    assert [json.loads(line)["data"] for line in (tmp_path / "events.jsonl").read_text().splitlines()] == [{"day": 3, "phase": "playing"}, {"deaths": 1}]
