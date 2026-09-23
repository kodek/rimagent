from __future__ import annotations

import re

import pytest

from agentv2.bridge import BridgeError


async def test_a_choice_letter_is_on_the_stack_and_in_the_ledger(game, bridge):
    letter_id = game.add_letter("Trade request", "Give 200 wood for 150 silver.", ["Accept", "Reject"], quest=7)
    game.add_letter("Heat wave")
    assert (await bridge.call("state.letters"))[0] == {"id": letter_id, "label": "Trade request", "def": "NewQuest", "tick": game.tick,
                                                      "text": "Give 200 wood for 150 silver.", "choices": ["Accept", "Reject"], "quest": 7}
    event = (await bridge.events(0))["events"][0]
    assert event["kind"] == "letter" and event["data"] == {"label": "Trade request", "def": "NewQuest", "text": "Give 200 wood for 150 silver.",
                                                           "id": letter_id, "quest": 7}
    with pytest.raises(BridgeError, match=re.escape("Available: Accept | Reject")):
        await bridge.call("ui.letter", {"id": letter_id, "action": "choose", "choice": "Maybe"})
    assert await bridge.call("ui.letter", {"id": letter_id, "action": "choose", "choice": "accept"}) == {"chose": "Accept", "letter": letter_id}
    assert [x["label"] for x in await bridge.call("state.letters")] == ["Heat wave"]


async def test_a_dialog_pauses_the_clock_until_it_is_answered(game, bridge):
    game.open_dialog("A wanderer asks to join.", ["Accept", "Reject"])
    dialogs = await bridge.call("state.dialogs")
    assert dialogs[0]["i"] == 0 and dialogs[0]["choices"][1] == {"i": 1, "label": "Reject", "disabled": False, "reason": None}
    assert (await bridge.events(0))["events"][0]["data"]["i"] == -1
    assert await bridge.call("ui.dialog", {"i": 0, "choice": 1}) == {"chose": "Reject", "next": None}
    assert game.ledger[-1]["kind"] == "dialog_answered" and game.ledger[-1]["text"] == "chose 'Reject'"
    with pytest.raises(BridgeError, match="no open dialog"):
        await bridge.call("ui.dialog", {"choice": "Accept"})


async def test_posture_is_set_read_and_cleared(game, bridge):
    posture = await bridge.call("steward.posture", {"preset": "defend", "hours": 6})
    assert posture["label"] == "defend" and posture["expires_in_hours"] == 6
    assert (await bridge.call("state.summary"))["steward"]["posture"] == "defend"
    assert (await bridge.call("steward.status"))["posture"]["label"] == "defend"
    with pytest.raises(BridgeError, match="unknown preset"):
        await bridge.call("steward.posture", {"preset": "panic"})
    assert await bridge.call("steward.posture", {"preset": "normal"}) is None
    assert game.posture is None
