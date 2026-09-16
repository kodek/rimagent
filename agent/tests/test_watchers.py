"""watchers.run_all with a fake ctx: alerts, actions through the bridge, error and timeout disabling."""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from rimagent import watchers
from rimagent.registry import Registry


class StubBridge:
    def __init__(self, ok: bool = True):
        self.calls: list[tuple[str, dict]] = []
        self.ok = ok

    def call_raw(self, method, params=None):
        self.calls.append((method, params))
        if self.ok:
            return {"ok": True, "result": {"did": method}}
        return {"ok": False, "error": "nope"}


def make_ctx(reg: Registry, ok: bool = True):
    events: list[tuple[str, dict]] = []
    bridge = StubBridge(ok)
    ctx = SimpleNamespace(registry=reg, bridge=bridge, emit=lambda kind, data: events.append((kind, data)), events=events)
    return ctx


def test_alert_and_action_watchers():
    reg = Registry()
    seen_events = []

    def alerter(ctx, events):
        seen_events.append(events)
        return [{"type": "alert", "text": "fire in the kitchen"}, {"type": "alert", "text": "quiet", "wake": False}, "junk", {"type": "other"}]

    def actor(ctx, events):
        return [{"type": "action", "method": "pawn.draft", "params": {"pawn": "Jen"}, "note": "raid"}]

    reg.watchers["alerter"] = alerter
    reg.watchers["actor"] = actor
    ctx = make_ctx(reg)

    alerts = watchers.run_all(ctx, [{"kind": "letter"}])

    assert seen_events == [[{"kind": "letter"}]]
    assert alerts == [
        {"watcher": "alerter", "text": "fire in the kitchen", "wake": True},
        {"watcher": "alerter", "text": "quiet", "wake": False},
    ]
    assert ctx.bridge.calls == [("pawn.draft", {"pawn": "Jen"})]
    kinds = [k for k, _ in ctx.events]
    assert kinds == ["watcher", "watcher", "watcher"]
    action_ev = next(d for _, d in ctx.events if "action" in d)
    assert action_ev == {"name": "actor", "action": "pawn.draft", "params": {"pawn": "Jen"}, "note": "raid", "ok": True, "result": {"did": "pawn.draft"}}
    alert_ev = next(d for _, d in ctx.events if "alert" in d)
    assert alert_ev == {"name": "alerter", "alert": "fire in the kitchen", "wake": True}
    assert reg.watcher_errors == {}


def test_action_with_wake_becomes_alert_and_bridge_error_is_reported():
    reg = Registry()
    reg.watchers["actor"] = lambda ctx, events: [{"type": "action", "method": "game.pause", "wake": True, "note": "pausing"}]
    ctx = make_ctx(reg, ok=False)

    alerts = watchers.run_all(ctx, [])
    assert alerts == [{"watcher": "actor", "text": "pausing", "wake": True}]
    assert ctx.bridge.calls == [("game.pause", {})]
    assert ctx.events[0][1]["ok"] is False
    assert ctx.events[0][1]["result"] == "nope"


def test_watcher_returning_none_is_fine():
    reg = Registry()
    reg.watchers["quiet"] = lambda ctx, events: None
    ctx = make_ctx(reg)
    assert watchers.run_all(ctx, []) == []
    assert ctx.events == []


def test_raising_watcher_is_disabled():
    reg = Registry()
    calls = {"n": 0}

    def bad(ctx, events):
        calls["n"] += 1
        raise RuntimeError("watcher exploded")

    reg.watchers["bad"] = bad
    reg.watchers["good"] = lambda ctx, events: [{"type": "alert", "text": "ok"}]
    ctx = make_ctx(reg)

    alerts = watchers.run_all(ctx, [])
    assert [a["watcher"] for a in alerts] == ["good"]
    assert "bad.py" in reg.watcher_errors
    assert "RuntimeError: watcher exploded" in reg.watcher_errors["bad.py"]
    err_ev = next(d for k, d in ctx.events if k == "watcher" and "error" in d)
    assert err_ev == {"name": "bad", "error": "RuntimeError: watcher exploded"}

    # disabled: not called again on the next tick
    watchers.run_all(ctx, [])
    assert calls["n"] == 1


def test_slow_watcher_times_out_and_is_disabled():
    # run_all's timeout is hardcoded at 4s, so this test takes ~4s by design.
    reg = Registry()
    release = threading.Event()
    calls = {"n": 0}

    def slow(ctx, events):
        calls["n"] += 1
        release.wait(10)
        return [{"type": "alert", "text": "too late"}]

    reg.watchers["slow"] = slow
    reg.watchers["fast"] = lambda ctx, events: [{"type": "alert", "text": "fast"}]
    ctx = make_ctx(reg)
    try:
        t0 = time.monotonic()
        alerts = watchers.run_all(ctx, [])
        elapsed = time.monotonic() - t0
    finally:
        release.set()  # free the pool thread so it does not linger for the full 10s

    assert 3.5 <= elapsed < 8
    assert [a["text"] for a in alerts] == ["fast"]
    assert reg.watcher_errors["slow.py"].startswith("timed out")
    assert ("watcher", {"name": "slow", "error": "timeout"}) in ctx.events

    watchers.run_all(ctx, [])
    assert calls["n"] == 1


# ---------------------------------------------------------------- superseded by a standing order

def test_superseded_watchers_are_skipped_but_not_errors():
    reg = Registry()
    calls = {"n": 0}

    def drafter(ctx, events):
        calls["n"] += 1
        return [{"type": "action", "method": "ui.draft", "params": {"pawn": "Jen", "drafted": True}}]

    reg.watchers["hostile_draft"] = drafter
    reg.watchers["mood_watch"] = lambda ctx, events: [{"type": "alert", "text": "sad"}]
    reg.set_superseded({"hostile_draft": "combat", "rescue_downed": "rescue"})   # not-loaded stems are kept in the map too
    ctx = make_ctx(reg)
    alerts = watchers.run_all(ctx, [{"kind": "hostile_group"}])
    assert [a["watcher"] for a in alerts] == ["mood_watch"]
    assert calls["n"] == 0 and ctx.bridge.calls == [] and reg.watcher_errors == {}
    # the order goes off: the watcher covers again
    reg.set_superseded({})
    watchers.run_all(ctx, [{"kind": "hostile_group"}])
    assert calls["n"] == 1 and ctx.bridge.calls == [("ui.draft", {"pawn": "Jen", "drafted": True})]
    # the director rewrote it: never superseded again this process
    reg.release_watcher("hostile_draft")
    assert reg.set_superseded({"hostile_draft": "combat", "fire_alert": "fire"}) == {"fire_alert": "fire"}
    watchers.run_all(ctx, [])
    assert calls["n"] == 2


def test_superseded_mapping_and_now():
    default = watchers.superseded_mapping(None)
    assert default == watchers.SUPERSEDED_WATCHERS and default is not watchers.SUPERSEDED_WATCHERS
    assert set(default) == {"hostile_draft", "undraft_after_fight", "fire_alert", "rescue_downed", "unforbid_drops_watcher", "rotting_corpses", "food_policy_watcher", "build_stall"}
    assert watchers.superseded_mapping({"my_drafter.py": "combat", "": "x", "z": None}) == {"my_drafter": "combat"}
    assert watchers.superseded_mapping(["hostile_draft", "custom.py"]) == {"hostile_draft": "combat", "custom": "orders"}
    assert watchers.superseded_mapping({}) == {} and watchers.superseded_mapping([]) == {}
    assert watchers.superseded_mapping("junk") == default
    m = {"hostile_draft": "combat", "rescue_downed": "rescue"}
    assert watchers.superseded_now(m, orders_supported=True, orders_on=True) == m
    assert watchers.superseded_now(m, orders_supported=True, orders_on=True, orders_off={"rescue"}) == {"hostile_draft": "combat"}
    assert watchers.superseded_now(m, orders_supported=False, orders_on=True) == {}     # older mod: watchers cover
    assert watchers.superseded_now(m, orders_supported=True, orders_on=False) == {}     # orders/steward off


def test_brain_watcher_tools_show_and_release_superseded(clean_brain):
    from rimagent import paths
    from rimagent.tools import brain as brain_tools

    (paths.WATCHERS / "hostile_draft.py").write_text("def watch(ctx, events):\n    return []\n", encoding="utf-8")
    (paths.WATCHERS / "mood_watch.py").write_text("def watch(ctx, events):\n    return []\n", encoding="utf-8")
    reg = Registry()
    reg.reload_brain()
    reg.set_superseded({"hostile_draft": "combat", "rescue_downed": "rescue"})
    ctx = make_ctx(reg)
    out = brain_tools.watcher_list(ctx)
    assert "- hostile_draft  (SUPERSEDED by the combat standing order" in out and "- mood_watch\n" in out
    assert "superseded (" in out and "hostile_draft -> combat" in out and "rescue_downed" not in out.split("superseded (")[1]
    assert "errors:\n(none)" in out
    # rewriting the file lifts the mark (and it is not re-applied by a later sync)
    brain_tools.watcher_write(ctx, "hostile_draft", "def watch(ctx, events):\n    return [{'type': 'alert', 'text': 'raid'}]\n")
    assert "hostile_draft" not in reg.watcher_superseded and "hostile_draft" in reg.watcher_kept
    assert reg.set_superseded({"hostile_draft": "combat"}) == {}
    assert "SUPERSEDED" not in brain_tools.watcher_list(ctx)
    # deleting a superseded file drops it from the map too
    reg.set_superseded({"mood_watch": "policies"})
    assert brain_tools.watcher_delete(ctx, "mood_watch") == "deleted"
    assert reg.watcher_superseded == {} and "mood_watch" not in reg.watchers
    # a vanished file (deleted outside the tools) is pruned on reload
    reg.set_superseded({"gone": "fire"})
    reg.reload_brain()
    assert reg.watcher_superseded == {}
