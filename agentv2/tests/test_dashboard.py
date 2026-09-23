from __future__ import annotations

import httpx
import pytest

from agentv2.dashboard.app import create_app
from agentv2.events import Log
from agentv2.runtime import open_runtime
from agentv2.scripted import call, scripted_model
from agentv2.wake import Wake


@pytest.fixture
async def client(settings, bridge, bus):
    async with open_runtime(settings, bus, bridge, scripted_model(lambda messages, info: call("end_turn", {"notes": "x"}))) as rt:
        await rt.runner.prepare()
        await rt.runner.ensure_game()
        app = create_app(bus, bridge, rt.brain_view, rt.controls)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://dashboard") as c:
            yield c, rt


async def test_page_and_state(client):
    c, _ = client
    assert "agentv2" in (await c.get("/")).text
    state = (await c.get("/api/state")).json()
    assert state["game"]["state"] == "playing" and state["controls"]["paused"] is False


async def test_brain_tree_and_files(client):
    c, _ = client
    tree = (await c.get("/api/brain/tree")).json()
    assert {s["name"] for s in tree["skills"]} >= {"defense-basics"}
    assert {w["name"] for w in tree["watchers"]} >= {"raid_prep"}
    assert tree["memory"]["doctrine"] > 1000 and tree["colony"] == "episode-001-rimagent-1"
    skill = (await c.get("/api/brain/file", params={"kind": "skill", "name": "defense-basics"})).json()
    assert skill["name"] == "SKILL.md" and "name: defense-basics" in skill["text"]
    assert (await c.get("/api/brain/file", params={"kind": "doctrine"})).json()["text"].startswith("# Doctrine")
    assert (await c.get("/api/brain/file", params={"kind": "skill", "name": "../AGENTS"})).status_code == 400
    assert (await c.get("/api/brain/file", params={"kind": "watcher", "name": "missing"})).status_code == 404


async def test_controls_and_operator(client, game):
    c, rt = client
    assert (await c.post("/api/control", json={"action": "pause"})).json()["paused"] is True
    assert rt.controls.paused
    assert (await c.post("/api/say", json={"text": "hello"})).json() == {"ok": True}
    assert rt.runner.inbox.operator == ["hello"] and rt.runner.inbox.forced == Wake("operator message", True)
    assert (await c.post("/api/control", json={"action": "nope"})).status_code == 400
    assert (await c.post("/api/control", json={"action": "order", "value": True})).status_code == 400
    assert (await c.post("/api/control", json={"action": "order", "id": "fire", "value": False})).json()["ok"] is True
    assert ("steward.orders.set", {"id": "fire", "enabled": False}) in game.calls
    assert (await c.post("/api/control", json={"action": "no_pause", "value": False})).json()["no_pause"] is False


async def test_the_loop_view_and_the_operator_stage_switch(client):
    c, rt = client
    view = (await c.get("/api/loop")).json()
    assert view["jev"] is None and view["directive"] is None and view["decisions"] == []
    assert {p["name"]: p["stage"] for p in view["policies"]}["dialogs"] == "shadow"
    assert (await c.post("/api/control", json={"action": "policy_stage", "name": "dialogs", "stage": "active"})).json()["ok"] is True
    assert rt.loop.stage(rt.loop.policies()["dialogs"]) == "active"
    assert (await c.post("/api/control", json={"action": "policy_stage", "name": "nope", "stage": "active"})).status_code == 404
    assert (await c.post("/api/control", json={"action": "loop", "value": False})).json()["ok"] is True and rt.loop.on is False
    tree = (await c.get("/api/brain/tree")).json()
    assert {p["name"] for p in tree["policies"]} >= {"dialogs", "letters"}
    assert "subject: dialogs" in (await c.get("/api/brain/file", params={"kind": "policy", "name": "dialogs"})).json()["text"]


async def test_events_and_bridge_views(client):
    c, rt = client
    rt.bus.emit(Log(text="hi"))
    events = (await c.get("/api/events", params={"kinds": "log"})).json()
    assert events[-1]["data"]["text"] == "hi"
    assert (await c.get("/api/base")).json()["home_center"] == [120, 120]
    shot = await c.get("/screenshot_marked.png")
    assert shot.headers["content-type"] == "image/png"
