from __future__ import annotations

import argparse

from test_runner import Script, prompts

from agentv2 import cli
from agentv2.bridge import Bridge
from agentv2.scripted import call, scripted_model


async def test_think_runs_one_step_and_pauses_the_game(settings, game, monkeypatch, capsys):
    script = Script()
    script.responses = [call("end_turn", {"notes": "one step", "wake_in_hours": 5})]
    monkeypatch.setattr(cli.config, "load", lambda: settings)
    monkeypatch.setattr(cli, "Bridge", lambda url, timeout: Bridge("http://fakegame", transport=game.transport()))
    monkeypatch.setattr(cli, "build_model", lambda llm: scripted_model(script))
    await cli._think(argparse.Namespace(trigger="debug", urgent=False))
    out = capsys.readouterr().out
    assert "notes: one step" in out and "'wake_in_hours': 5.0" in out and game.paused
    assert "## Wake trigger\ndebug" in prompts(script.received[0])
