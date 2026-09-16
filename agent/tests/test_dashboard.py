from __future__ import annotations

from fastapi.testclient import TestClient

from rimagent.bus import Bus
from rimagent.dashboard.app import create_app


class FakeBridge:
    def status(self):
        return {"state": "menu"}

    def events(self, since: int, limit: int = 500):
        return {"events": []}

    def screenshot(self, x=None, z=None, w=60, **_):
        raise RuntimeError("no game")

    def call(self, method, **params):
        raise RuntimeError(f"unknown method {method}")


class FakeControls:
    def __init__(self):
        self.paused = False
        self.calls: list[tuple] = []

    def pause(self):
        self.paused = True
        self.calls.append(("pause",))

    def resume(self):
        self.paused = False
        self.calls.append(("resume",))

    def think_now(self):
        self.calls.append(("think_now",))

    def set_no_pause(self, v: bool):
        self.calls.append(("set_no_pause", v))

    steward = True
    orders_off: list[str] = []

    def set_steward(self, v: bool):
        self.steward = v
        self.calls.append(("set_steward", v))

    def set_order(self, order_id: str, v: bool):
        self.orders_off = sorted((set(self.orders_off) | {order_id}) if not v else (set(self.orders_off) - {order_id}))
        self.calls.append(("set_order", order_id, v))
        return {"id": order_id, "enabled": v}

    def set_rally(self, rect):
        self.calls.append(("set_rally", rect))
        return {"rect": rect} if rect else None


def _client():
    bus = Bus(log_file=False)
    controls = FakeControls()
    app = create_app(bus, FakeBridge(), controls)
    return TestClient(app), bus, controls


def test_index_html():
    c, _, _ = _client()
    r = c.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "<title>rimagent</title>" in r.text
    assert "/stream" in r.text


def test_events_roundtrip():
    c, bus, _ = _client()
    bus.emit("think_start", {"trigger": "test", "step": 1})
    bus.emit("assistant", {"text": "hello"})
    bus.emit("status", {"phase": "thinking", "episode": 2})
    evs = c.get("/api/events?since=0").json()
    assert [e["kind"] for e in evs] == ["think_start", "assistant", "status"]
    assert evs[1]["data"]["text"] == "hello"
    only = c.get("/api/events?since=1&kinds=status").json()
    assert [e["kind"] for e in only] == ["status"]
    st = c.get("/api/state").json()
    assert st["bus"]["phase"] == "thinking"
    assert st["last_seq"] == 3
    assert st["game"] == {"state": "menu"}


def test_brain_file_rejects_traversal():
    c, _, _ = _client()
    assert c.get("/api/brain/file", params={"kind": "skill", "name": "../../config.yaml"}).status_code == 400
    assert c.get("/api/brain/file", params={"kind": "tool", "name": "/etc/passwd"}).status_code == 400
    assert c.get("/api/brain/file", params={"kind": "watcher", "name": "..%2F..%2Fpyproject.toml"}).status_code in (400, 404)
    assert c.get("/api/brain/file", params={"kind": "bogus", "name": "x"}).status_code == 400
    assert c.get("/api/brain/file", params={"kind": "skill", "name": "definitely-not-a-skill-xyz"}).status_code == 404
    tree = c.get("/api/brain/tree").json()
    assert set(tree) >= {"skills", "tools", "watchers", "notebook_chars", "journal_chars"}


def test_control_pause():
    c, _, controls = _client()
    r = c.post("/api/control", json={"action": "pause"})
    assert r.status_code == 200 and r.json()["ok"] and r.json()["paused"] is True
    assert controls.calls == [("pause",)]
    r = c.post("/api/control", json={"action": "no_pause", "value": True})
    assert r.json()["ok"] and controls.calls[-1] == ("set_no_pause", True)
    # missing method is handled defensively, not a 500
    r = c.post("/api/control", json={"action": "kill"})
    assert r.status_code == 200 and r.json()["ok"] is False
    assert c.post("/api/control", json={"action": "nope"}).status_code == 400


def test_misc_endpoints():
    c, _, _ = _client()
    assert c.get("/screenshot.png").status_code == 503
    assert c.get("/api/ledger?since=0").json() == {"events": []}
    assert isinstance(c.get("/api/scores").json(), list)
    assert c.get("/api/git/log").status_code == 200
    assert c.get("/api/git/diff?sha=..%2Fx").status_code == 400


def test_steward_tab_and_control():
    c, _, controls = _client()
    assert "Steward" in c.get("/").text and "loadSteward" in c.get("/").text
    r = c.get("/api/steward")
    assert r.status_code == 503 and r.json()["unavailable"] is True
    r = c.post("/api/control", json={"action": "steward", "value": False})
    assert r.json()["ok"] and controls.calls[-1] == ("set_steward", False)
    assert c.get("/api/state").json()["controls"]["steward"] is False


def test_steward_endpoint_returns_status_with_research():
    class Bridge(FakeBridge):
        def call(self, method, **params):
            if method == "steward.status":
                return {"enabled": {"scorer": True, "stock": True}, "posture": None, "pawns": [], "stock": [], "problems": []}
            raise RuntimeError("no steward.research")

    bus = Bus(log_file=False)
    c = TestClient(create_app(bus, Bridge(), FakeControls()))
    j = c.get("/api/steward").json()
    assert j["enabled"] == {"scorer": True, "stock": True} and j["research"] is None


def test_steward_orders_controls_and_table():
    c, _, controls = _client()
    html = c.get("/").text
    assert "Standing orders" in html and "control('order'" in html and "setRally" in html and "rally-x" in html
    r = c.post("/api/control", json={"action": "order", "id": "corpses", "value": False})
    assert r.json()["ok"] and r.json()["result"] == {"id": "corpses", "enabled": False}
    assert controls.calls[-1] == ("set_order", "corpses", False)
    assert c.get("/api/state").json()["controls"]["orders_off"] == ["corpses"]
    assert c.post("/api/control", json={"action": "order", "value": True}).status_code == 400
    r = c.post("/api/control", json={"action": "rally", "rect": [40, 40, 6, 6]})
    assert r.json()["ok"] and r.json()["result"] == {"rect": [40, 40, 6, 6]} and controls.calls[-1] == ("set_rally", [40, 40, 6, 6])
    r = c.post("/api/control", json={"action": "rally"})
    assert r.json()["ok"] and r.json()["result"] is None and controls.calls[-1] == ("set_rally", None)

    class Bridge(FakeBridge):
        rich = True

        def call(self, method, **params):
            if method == "steward.status":
                return {"enabled": {"scorer": True, "stock": True}, "posture": None, "pawns": [], "stock": [], "problems": [],
                        "orders": [{"id": "combat", "enabled": True, "summary": "no hostiles", "acting_on": 0}], "rally": [40, 40, 6, 6]}
            if method == "steward.orders" and self.rich:
                # the full rows (label, interval, last run) only steward.orders carries; the Orders table renders them
                return [{"id": "combat", "label": "Combat", "enabled": True, "interval_ticks": 60, "last_run_hours_ago": 0.25, "summary": "no hostiles", "acting_on": 0},
                        {"id": "rescue", "label": "Rescue", "enabled": True, "interval_ticks": 300, "last_run_hours_ago": 0.1, "summary": None, "acting_on": 0}]
            raise RuntimeError("no such method")

    j = TestClient(create_app(Bus(log_file=False), Bridge(), FakeControls())).get("/api/steward").json()
    assert j["rally"] == [40, 40, 6, 6] and [o["id"] for o in j["orders"]] == ["combat", "rescue"]
    assert j["orders"][0]["label"] == "Combat" and j["orders"][0]["interval_ticks"] == 60 and j["orders"][0]["last_run_hours_ago"] == 0.25
    # an older mod without steward.orders: the compact steward.status rows stay
    b = Bridge(); b.rich = False
    j2 = TestClient(create_app(Bus(log_file=False), b, FakeControls())).get("/api/steward").json()
    assert j2["orders"] == [{"id": "combat", "enabled": True, "summary": "no hostiles", "acting_on": 0}]
