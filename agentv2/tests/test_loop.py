from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo

from agentv2.events import ToolCall, ToolResult
from agentv2.loop.directive import TICKS_PER_HOUR, Directive, Priority
from agentv2.loop.engine import evaluate
from agentv2.loop.fakejev import FakeJev, lean
from agentv2.loop.gate import Gate
from agentv2.loop.jev import ChoiceAnswer, NoulAnswer, ScoreAnswer
from agentv2.loop.spec import REPORT_UP, parse
from agentv2.loop.subjects import Entity
from agentv2.runtime import open_runtime
from agentv2.scripted import call, code, scripted_model
from agentv2.wake import Wake

SEEDS = {"dialogs", "letters", "posture", "event-triage"}
SEED_POLICIES = Path(__file__).resolve().parents[1] / "brain" / "policies"


class Script:
    def __init__(self) -> None:
        self.responses: list[ModelResponse] = []
        self.received: list[list[ModelMessage]] = []

    def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.received.append(list(messages))
        return self.responses.pop(0)


@pytest.fixture
async def looped(settings, bridge, bus):
    jev, script = FakeJev(), Script()
    async with open_runtime(settings, bus, bridge, scripted_model(script), jev) as rt:
        await rt.runner.prepare()
        await rt.runner.ensure_game()
        await rt.runner.poller.poll_once(rt.runner.episode)
        yield rt, jev, script


def direct(rt, game, **over) -> Directive:
    rt.runner.episode.directive = Directive(**({"version": 1, "base_tick": game.tick, "expires_tick": game.tick + 24 * TICKS_PER_HOUR,
                                                "purpose": "Survive the first winter", "never": ["Never let a raider join."],
                                                "priorities": [Priority(name="food", statement="Keep more than 5 days of meals.")]} | over))
    return rt.runner.episode.directive


def answer(name: str, label: str | None = None, p: float = 0.9):
    """A FakeJev responder for question `name`, in whatever policy asks it."""
    return lambda state, qs: {name: lean(qs[name], label, p)} if name in qs else {}


def prompts(messages: list[ModelMessage]) -> str:
    return "\n".join(str(p.content) for m in messages for p in getattr(m, "parts", []) if p.part_kind == "user-prompt")


def decisions(rt, policy: str):
    return rt.loop.store.recent(policy, 50)


async def test_the_seed_policies_are_valid_and_start_in_shadow(looped):
    rt, _, _ = looped
    policies = rt.loop.policies()
    assert set(policies) == SEEDS
    assert all(p.spec is not None for p in policies.values()), {p.name: p.error for p in policies.values()}
    assert {rt.loop.stage(p) for p in policies.values()} == {"shadow"}


async def test_an_active_policy_answers_a_dialog_and_the_director_is_not_woken(looped, game):
    rt, jev, _ = looped
    direct(rt, game)
    rt.loop.set_stage("dialogs", "active", "test")
    game.open_dialog("A wanderer asks to join. She is a skilled cook.", ["Accept", "Reject"])
    urgent: list[list[str]] = []
    rt.runner.poller.on_urgent = lambda items: urgent.append(items) or asyncio.sleep(0)
    await rt.runner.poller.poll_once(rt.runner.episode)
    dialog = next(e for e in rt.runner.inbox.events if e["kind"] == "dialog")
    assert rt.loop.holds(dialog) and urgent == []
    await rt.loop.tick_once()
    assert game.dialogs == [] and ("ui.dialog", {"i": 0, "choice": "Accept"}) in game.calls
    acted = decisions(rt, "dialogs")[0]
    assert acted.outcome == "acted" and acted.label == "Accept" and acted.state["directive"]["never"] == ["Never let a raider join."]
    assert "Survive the first winter" in str(jev.calls[-1][0])
    await rt.runner.poller.poll_once(rt.runner.episode)
    await rt.loop.tick_once()
    assert rt.loop.store.get(acted.id).truth is None, "its own answer is not a label"
    wake = rt.runner.wake.check(game.tick, [], [e for e in rt.runner.inbox.events if not rt.loop.holds(e)], None)
    assert wake is None or "dialog" not in wake.trigger


async def test_a_shadow_policy_only_watches_and_the_directors_answer_labels_it(looped, game):
    rt, _, script = looped
    direct(rt, game)
    letter = game.add_letter("Trade request", "Give 200 wood for 150 silver.", ["Accept", "Reject"], quest=1)
    await rt.runner.poller.poll_once(rt.runner.episode)
    assert not any(rt.loop.holds(e) for e in rt.runner.inbox.events)
    await rt.loop.tick_once()
    shadow = decisions(rt, "letters")[0]
    assert shadow.outcome == "shadow" and shadow.label == "Accept" and [x["id"] for x in game.letters] == [letter]
    script.responses = [code(f"await rw_ui_letter(id={letter}, action='choose', choice='Reject')"), call("end_turn", {"notes": "no trade"})]
    await rt.runner.step(Wake("letter", False))
    report = prompts(script.received[0])
    assert "## Fast loop (Jev policies)" in report and "letters [shadow]" in report and "Trade request" in report
    await rt.loop.tick_once()
    labelled = rt.loop.store.get(shadow.id)
    assert labelled.truth == "Reject" and labelled.truth_source == "director"


async def test_doubt_and_vetoes_escalate_and_without_a_directive_it_only_watches(looped, game):
    rt, jev, _ = looped
    rt.loop.set_stage("letters", "active", "test")
    game.add_letter("Refugee", "A refugee asks for shelter. Pirates chase her.", ["Accept", "Reject"])
    await rt.runner.poller.poll_once(rt.runner.episode)
    await rt.loop.tick_once()
    first = decisions(rt, "letters")[0]
    assert first.outcome == "shadow" and "no valid directive" in first.reason and game.letters
    direct(rt, game)
    jev.respond = answer("risks_colonists")
    game.add_letter("Guests", "Two travellers ask to stay.", ["Accept", "Reject"])
    await rt.runner.poller.poll_once(rt.runner.episode)
    await rt.loop.tick_once()
    vetoed = [d for d in decisions(rt, "letters") if d.outcome == "escalated"]
    assert vetoed and all("veto risks_colonists" in d.reason for d in vetoed)
    alert = rt.runner.inbox.alerts[-1]
    assert alert.watcher == "fast loop/letters" and alert.wake and "decision" in alert.text
    jev.respond = answer("reply", "Accept", 0.4)
    game.add_letter("Trader", "A caravan wants to trade.", ["Accept", "Reject"])
    await rt.runner.poller.poll_once(rt.runner.episode)
    await rt.loop.tick_once()
    assert any(d.outcome == "escalated" and "confidence" in d.reason for d in decisions(rt, "letters"))
    assert all(x["label"] in ("Refugee", "Guests", "Trader") for x in game.letters), "nothing was answered"


async def test_a_jev_outage_releases_a_claimed_dialog_and_the_director_hears_at_once(looped, game):
    rt, jev, _ = looped
    direct(rt, game)
    rt.loop.set_stage("dialogs", "active", "test")
    game.open_dialog("A raider surrenders.", ["Imprison", "Release"])
    await rt.runner.poller.poll_once(rt.runner.episode)
    dialog = next(e for e in rt.runner.inbox.events if e["kind"] == "dialog")
    assert rt.loop.holds(dialog)
    jev.available = False
    await rt.loop.tick_once()
    await asyncio.sleep(0)
    assert not rt.loop.holds(dialog)
    assert any("did not handle" in a.text for a in rt.runner.inbox.alerts)
    assert rt.runner.wake.check(game.tick, [], [dialog], None).urgent
    assert rt.loop.observe([{**dialog, "seq": 999}]) == set(), "it claims nothing while Jev is down"


async def test_posture_changes_only_on_a_new_choice_and_yields_to_the_director(looped, game, bus):
    rt, jev, _ = looped
    direct(rt, game)
    rt.loop.set_stage("posture", "active", "test")
    await rt.loop.tick_once()
    assert not [c for c in game.calls if c[0] == "steward.posture"], "normal is in force, so nothing changes"
    jev.respond = answer("posture", "defend")
    game.advance(2)
    await rt.runner.poller.poll_once(rt.runner.episode)
    await rt.loop.tick_once()
    assert ("steward.posture", {"preset": "defend", "hours": 6.0}) in game.calls and game.posture["label"] == "defend"
    bus.emit(ToolCall(name="rw_steward_posture", args={"preset": "build"}, id="p1", parent="r1"), stream="play")
    bus.emit(ToolResult(name="rw_steward_posture", id="p1", parent="r1", ok=True, text="{}", elapsed=0.1), stream="play")
    jev.respond = answer("posture", "harvest")
    game.advance(4)
    await rt.runner.poller.poll_once(rt.runner.episode)
    await rt.loop.tick_once()
    assert [c for c in game.calls if c[0] == "steward.posture"] == [("steward.posture", {"preset": "defend", "hours": 6.0})]


async def test_the_gate_needs_heldout_agreement_then_clean_canary_actions(looped, game, settings):
    rt, jev, _ = looped
    settings.loop.gate.canary_actions, settings.loop.gate.min_heldout = 1, 3
    gate = Gate(rt.loop, jev, settings.loop.gate, settings.loop.report_up_threshold)
    refused = await gate.promote("letters")
    assert not refused["promoted"] and "held-out labels" in refused["why"]
    direct(rt, game)
    for i in range(16):
        game.add_letter(f"Offer {i}", f"Trade offer number {i}.", ["Accept", "Reject"])
    await rt.runner.poller.poll_once(rt.runner.episode)
    await rt.loop.tick_once()
    shadow = decisions(rt, "letters")
    assert len(shadow) == 16
    for d in shadow:
        assert rt.loop.label(d.id, "Accept", "improver")
    assert len(rt.loop.store.labelled("letters", heldout=True)) >= 3
    promoted = await gate.promote("letters")
    assert promoted["promoted"] and promoted["stage"] == "canary" and promoted["evidence"]["agreement"] == 1.0
    visible = await gate.replay_visible("letters")
    assert visible.agreement == 1.0 and visible.changed == 0 and all("truth" in r for r in visible.rows)
    game.add_letter("Canary offer", "One more offer.", ["Accept", "Reject"])
    await rt.runner.poller.poll_once(rt.runner.episode)
    await rt.loop.tick_once()
    assert decisions(rt, "letters")[0].outcome == "acted"
    assert (await gate.promote("letters"))["stage"] == "active"


async def test_wrong_labels_on_actions_demote_and_an_edit_starts_a_new_version_in_shadow(looped, game, settings):
    rt, _, _ = looped
    direct(rt, game)
    rt.loop.set_stage("letters", "active", "test")
    for i in range(2):
        game.add_letter(f"Offer {i}", "Trade offer.", ["Accept", "Reject"])
    await rt.runner.poller.poll_once(rt.runner.episode)
    await rt.loop.tick_once()
    for d in decisions(rt, "letters"):
        assert d.outcome == "acted"
        rt.loop.label(d.id, "Reject", "operator")
    policy = rt.loop.policies()["letters"]
    assert rt.loop.stage(policy) == "shadow"
    rt.loop.set_stage("letters", "active", "test")
    path = settings.brain / "policies" / "letters.yaml"
    path.write_text(path.read_text() + "\n# edited\n")
    (settings.brain / "policies" / "broken.yaml").write_text("subject: letters\n")
    rt.loop.repository.scan()
    assert rt.loop.stage(rt.loop.policies()["letters"]) == "shadow"
    assert "policy broken" in rt.loop.problems()


async def test_the_director_reads_and_labels_decisions_with_tools(looped, game, bus):
    rt, _, script = looped
    direct(rt, game)
    game.add_letter("Trade request", "Give 200 wood for 50 silver.", ["Accept", "Reject"])
    await rt.runner.poller.poll_once(rt.runner.episode)
    await rt.loop.tick_once()
    d = decisions(rt, "letters")[0]
    script.responses = [code("s = await loop_status()\nrows = await list_decisions(policy='letters', show='unlabelled')\n"
                             f"await label_decisions(labels=[{{'id': {d.id}, 'truth': 'Reject', 'note': 'too cheap'}}])\n"
                             "tried = await test_policy(name='letters')\n[s['on'], len(rows), tried]"),
                        call("end_turn", {"notes": "labelled"})]
    await rt.runner.step(Wake("check", False))
    results = [e["data"] for e in bus.since(0, kinds={ToolResult.KIND}) if e["data"]["name"] in ("loop_status", "list_decisions", "label_decisions", "test_policy")]
    assert len(results) == 4 and all(r["ok"] for r in results), results
    labelled = rt.loop.store.get(d.id)
    assert labelled.truth == "Reject" and labelled.truth_source == "director"


async def test_the_director_sets_the_directive_with_a_tool(looped, game):
    rt, _, script = looped
    script.responses = [code("await set_directive(purpose='Survive', priorities=[{'name': 'food', 'statement': 'Keep 5 days of meals.'}], "
                             "never=['Never sell medicine.'], report_when=['A colonist could die.'], hours=12)"),
                        call("end_turn", {"notes": "directive set"})]
    await rt.runner.step(Wake("first step", False))
    directive = rt.runner.episode.directive
    assert directive.version == 1 and directive.never == ["Never sell medicine."]
    assert directive.expires_tick == directive.base_tick + 12 * TICKS_PER_HOUR
    assert rt.runner.episodes.load().directive == directive


def test_the_rule_reports_up_first_and_skips_an_unchanged_choice():
    spec = parse("posture", (SEED_POLICIES / "posture.yaml").read_text()).spec
    entity = Entity("colony", "posture", {}, ("normal", "defend"), current="defend")
    choice = ChoiceAnswer(type="choice", choice="defend", confidence=0.9, probabilities={"defend": 0.95})
    calm = {"posture": choice, "breaks_rule": NoulAnswer(type="noul", noul=0.1)}
    assert evaluate(spec, entity, calm, 0.7).reason == "no change"
    assert evaluate(spec, entity, calm | {REPORT_UP: NoulAnswer(type="noul", noul=0.8)}, 0.7).outcome == "escalate"
    assert evaluate(spec, entity, calm | {"breaks_rule": NoulAnswer(type="noul", noul=0.6)}, 0.7).reason.startswith("veto")
    triage = parse("t", (SEED_POLICIES / "event-triage.yaml").read_text()).spec
    quiet = {"needs_leader": NoulAnswer(type="noul", noul=0.2), "urgency": ScoreAnswer(type="score", score=2.7, confidence=0.8)}
    assert evaluate(triage, Entity("event:1", "e", {}), quiet, 0.7).reason == "urgency 2.70 >= 2.5"


@pytest.mark.parametrize(("text", "problem"), [
    (("subject: events\ndescription: d\ntriggers: {events: [letter]}\nquestions: {q: {type: choice, instructions: i, criteria: {a: x, escalate: y}}}\n"
      "decide: {act_with: q, vetoes: {q: 0.5}}"), "cannot act"),
    (("subject: letters\ndescription: d\ntriggers: {events: [letter]}\nquestions: {q: {type: choice, instructions: i, options_from_subject: true}}\n"
      "decide: {act_with: q}"), "'escalate' label"),
    (("subject: letters\ndescription: d\ntriggers: {events: [letter]}\nquestions: {q: {type: choice, instructions: i, criteria: {escalate: y}, "
      "options_from_subject: true}}\ndecide: {act_with: q}"), "needs at least one veto"),
    ("subject: posture\ndescription: d\ntriggers: {every_hours: 1}\nclaims: [dialog]\nquestions: {q: {type: noul, instructions: i}}", "can claim only"),
    ("subject: events\ndescription: d\ntriggers: {events: [x]}\nfeatures: [luck]\nquestions: {q: {type: noul, instructions: i}}", "unknown feature"),
])
def test_invalid_policies_say_what_is_wrong(text, problem):
    policy = parse("p", text)
    assert policy.spec is None and problem in (policy.error or "")


def test_yaml_booleans_are_noul_criteria_keys():
    policy = parse("p", "subject: events\ndescription: d\ntriggers: {events: [x]}\nquestions:\n  q:\n    type: noul\n    instructions: i\n"
                        "    criteria:\n      true: it is so\n      false: it is not\n")
    assert policy.spec and policy.spec.questions["q"].criteria == {"true": "it is so", "false": "it is not"}
