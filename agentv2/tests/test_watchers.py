from __future__ import annotations

import pytest

from agentv2.watchers import Alert, Watcher, WatcherError, Watchers


@pytest.fixture
async def watchers(tmp_path, bridge, bus):
    async with Watchers(tmp_path, bridge, bus) as w:
        yield w


def write(watchers: Watchers, name: str, source: str) -> None:
    (watchers.repository.directory / f"{name}.py").write_text(source, encoding="utf-8")


async def test_alert_and_action(watchers, game, bus):
    write(watchers, "raid", 'def watch(events, status, memo):\n'
                            '    out = []\n'
                            '    for e in events:\n'
                            '        if e["kind"] == "hostile_group":\n'
                            '            out.append({"type": "action", "method": "game.speed", "params": {"speed": 1}})\n'
                            '            out.append({"type": "alert", "text": "RAID", "wake": True})\n'
                            '    return out\n')
    alerts = await watchers.run_all([{"kind": "hostile_group", "text": "pirates"}], {})
    assert alerts == [Alert("raid", "RAID", True)]
    assert ("game.speed", {"speed": 1}) in game.calls


async def test_actions_reserved_for_the_runner_or_dev_are_refused(watchers, game, bus):
    write(watchers, "rogue", 'def watch(events, status, memo):\n'
                             '    return [{"type": "action", "method": "game.quit_to_menu"}, {"type": "action", "method": "dev.kill_hostiles"}]\n')
    await watchers.run_all([], {})
    assert not [m for m, _ in game.calls if m in ("game.quit_to_menu", "dev.kill_hostiles")]
    results = [e["data"] for e in bus.since(0, kinds={"watcher"}) if "action" in e["data"]]
    assert [r["ok"] for r in results] == [False, False] and "reserved for the runner" in results[0]["result"]


async def test_memo_persists_and_rpc_reads(watchers):
    write(watchers, "count", 'async def watch(events, status, memo):\n'
                             '    memo["n"] = memo.get("n", 0) + 1\n'
                             '    s = await rpc("state.summary", {})\n'
                             '    return [{"type": "alert", "text": str(memo["n"]) + "/" + str(s["colonists"]), "wake": False}]\n')
    await watchers.run_all([], {})
    alerts = await watchers.run_all([], {})
    assert alerts[0].text == "2/3"


async def test_rpc_is_read_only(watchers):
    write(watchers, "bad", 'async def watch(events, status, memo):\n    await rpc("ui.draft", {"pawn": "Bob"})\n    return []\n')
    await watchers.run_all([], {})
    error = watchers.repository.loaded["bad"].error
    assert error and "PermissionError" in error and "return an action instead" in error


async def test_sandbox_blocks_the_host_and_runaway_loops(watchers):
    with pytest.raises(WatcherError, match="PermissionError"):
        await watchers.sandbox.evaluate(Watcher("fs", "import os\ndef watch(e, s, m):\n    return os.listdir('/')\n", "d"), [], {}, {})
    with pytest.raises(WatcherError, match="time limit"):
        await watchers.sandbox.evaluate(Watcher("loop", "def watch(e, s, m):\n    while True:\n        pass\n", "d"), [], {}, {})


async def test_failed_watcher_is_disabled_until_its_file_changes(watchers):
    write(watchers, "w", "def watch(events, status, memo):\n    return 1 / 0\n")
    await watchers.run_all([], {})
    error = watchers.repository.loaded["w"].error
    assert error and "ZeroDivisionError" in error
    assert watchers.errors() == {"watcher w": error}
    write(watchers, "w", "def watch(events, status, memo):\n    return []\n")
    await watchers.run_all([], {})
    assert watchers.repository.loaded["w"].error is None


async def test_wrong_return_type(watchers):
    with pytest.raises(WatcherError, match="list of dicts"):
        await watchers.sandbox.evaluate(Watcher("x", "def watch(e, s, m):\n    return ['no']\n", "d"), [], {}, {})
    with pytest.raises(WatcherError, match="list of dicts"):
        await watchers.sandbox.evaluate(Watcher("y", "def watch(e, s, m):\n    return [{'type': 'shout'}]\n", "d"), [], {}, {})


async def test_dry_run_carries_out_nothing_and_re_enables(watchers, game):
    write(watchers, "w", "def watch(events, status, memo):\n    return 1 / 0\n")
    await watchers.run_all([], {})
    write(watchers, "w", 'def watch(events, status, memo):\n    print("hi")\n    return [{"type": "action", "method": "game.speed", "params": {"speed": 1}}]\n')
    result = await watchers.dry_run("w", [], {})
    assert result["output"] == [{"type": "action", "method": "game.speed", "params": {"speed": 1}, "wake": False}]
    assert "hi" in "".join(result["prints"])
    assert not any(method == "game.speed" for method, _ in game.calls)
    with pytest.raises(LookupError):
        await watchers.dry_run("missing", [], {})


async def test_seed_watchers_run(settings, bridge, bus):
    async with Watchers(settings.brain / "watchers", bridge, bus) as w:
        events = [{"kind": "hostile_group", "text": "pirates"}, {"kind": "built", "text": "fueled stove", "thing": "FueledStove1"},
                  {"kind": "message", "text": "Bob slept outside"}, {"kind": "day", "text": "day 2"}]
        alerts = await w.run_all(events, {})
        assert not w.errors()
        assert {a.watcher for a in alerts} == {"raid_prep", "shelter_guard"}
