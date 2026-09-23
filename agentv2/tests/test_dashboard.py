from __future__ import annotations

import httpx
import pytest

from agentv2.dashboard.app import create_app
from agentv2.events import Log
from agentv2.runner import Runner
from agentv2.scripted import call, scripted_model


@pytest.fixture
async def client(settings, bridge, bus):
    runner = Runner(settings, bus, bridge, scripted_model(lambda messages, info: call("end_turn", {"notes": "x"})))
    async with runner.watchers:
        await runner.prepare()
        await runner.ensure_game()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(runner)), base_url="http://dashboard") as c:
            yield c, runner


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


async def test_controls_and_operator(client):
    c, runner = client
    assert (await c.post("/api/control", json={"action": "pause"})).json()["paused"] is True
    assert runner.agent_paused
    assert (await c.post("/api/say", json={"text": "hello"})).json() == {"ok": True}
    assert runner.operator_queue == ["hello"] and runner.force == "operator message"
    assert (await c.post("/api/control", json={"action": "nope"})).status_code == 400


async def test_events_and_bridge_views(client):
    c, runner = client
    runner.bus.emit(Log(text="hi"))
    events = (await c.get("/api/events", params={"kinds": "log"})).json()
    assert events[-1]["data"]["text"] == "hi"
    assert (await c.get("/api/base")).json()["home_center"] == [120, 120]
    shot = await c.get("/screenshot_marked.png")
    assert shot.headers["content-type"] == "image/png"
