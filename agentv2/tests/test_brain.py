from __future__ import annotations

from agentv2.brain import Brain
from agentv2.bus import Bus
from agentv2.history import Scores, score


def test_seed_brain_is_valid(settings):
    brain = Brain(settings.brain)
    caps = brain.run_capabilities()
    assert caps.errors == {}
    assert len(caps.skills) == 1 and caps.authored == []
    assert {s.name for s in brain.skills()} >= {"defense-basics", "early-game-food", "work-priorities"}
    assert brain.doctrine.read_text().startswith("# Doctrine")


def test_a_bad_skill_is_reported_and_the_others_still_load(settings):
    brain = Brain(settings.brain)
    bad = brain.skills_dir / "broken"
    bad.mkdir()
    (bad / "SKILL.md").write_text("no frontmatter here\n", encoding="utf-8")
    caps = brain.run_capabilities()
    assert list(caps.errors) == ["skill broken"]
    assert len(caps.skills) == 1


def test_authored_capability_round_trip(settings):
    brain = Brain(settings.brain)
    code = ("from dataclasses import dataclass\nfrom pydantic_ai.capabilities import AbstractCapability\n"
            "@dataclass\nclass Hello(AbstractCapability):\n    def get_instructions(self):\n        return 'hello'\n")
    record = brain.store.write("hello", code)
    assert record.last_error is None
    assert len(brain.run_capabilities().authored) == 1
    assert brain.authored()[0]["name"] == "hello"


def test_scores(settings):
    scores = Scores(settings.brain / "scores.jsonl")
    scores.record({"episode": 1, "seed": "s", "score": score(10, 3, 0, 15_000, 60, 4, 1)})
    assert scores.history()[0]["score"] == 100 + 180 + 2.5 + 30 + 32 + 40
    assert "episode | seed" in scores.text()


def test_bus_keeps_persistent_events_and_streams_ephemeral_ones():
    bus = Bus()
    queue = bus.subscribe()
    bus.emit("status", {"day": 3})
    bus.emit("delta", {"text": "thinking…"}, ephemeral=True)
    assert [e["kind"] for e in bus.since(0)] == ["status"]
    assert bus.state["day"] == 3
    assert [queue.get_nowait()["kind"] for _ in range(2)] == ["status", "delta"]
