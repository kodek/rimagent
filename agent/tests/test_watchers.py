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
