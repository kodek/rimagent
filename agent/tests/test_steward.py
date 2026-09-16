"""Steward on the Python side: packet block, roles allow-lists, config defaults, bridge doc notes."""
from __future__ import annotations

from pathlib import Path

from rimagent import config as config_mod
from rimagent import loop, roles
from rimagent.bridge import BridgeError
from rimagent.context import Context
from rimagent.registry import BRIDGE_DOC_NOTES, Registry, Tool

SAMPLE_STATUS = {
    "enabled": {"scorer": True, "stock": True},
    "posture": {"label": "winter prep", "expires_in_hours": 36.0, "work": {"Growing": 0.5, "Construction": -0.2}, "weights": {}, "targets": {"forestry": 1.5}},
    "pawns": [
        {"id": "Thing_Human_1", "name": "Jen", "managed": True, "priorities": {"Growing": 1, "Cooking": 2}, "top": [{"work": "Growing", "priority": 1, "why": "passion; crops ready"}]},
        {"id": "Thing_Human_2", "name": "Bob", "managed": False, "priorities": {"Construction": 1, "Mining": 2, "Hauling": 3, "Cleaning": 4, "Research": 4}, "top": []},
    ],
    "stock": [
        {"id": "j1", "kind": "forestry", "label": "wood", "target": 500, "current": 420, "enabled": True, "suspended": False, "managed": True, "last_run_hours_ago": 2.0, "designations": 6, "failures": 0, "summary": None, "notes": []},
        {"id": "j2", "kind": "hunting", "label": "meat", "target": 200, "current": 40, "enabled": True, "suspended": False, "managed": True, "last_run_hours_ago": 5.0, "designations": 0, "failures": 3, "summary": "no safe hunting targets", "notes": []},
        {"id": "j3", "kind": "mining", "label": "steel", "target": 300, "current": 120, "enabled": True, "suspended": True, "managed": True, "last_run_hours_ago": None, "designations": 0, "failures": 0, "summary": None, "notes": []},
    ],
    "problems": ["hunting: no safe hunting targets for a day", "Bob is unmanaged with Research at 4"],
}


class FakeBridge:
    def __init__(self, status=SAMPLE_STATUS, fail=False):
        self._status, self._fail = status, fail
        self.calls: list[str] = []

    def call(self, method, **params):
        self.calls.append(method)
        if method == "steward.status":
            if self._fail:
                raise BridgeError("unknown method steward.status")
            return self._status
        if method in ("state.summary", "state.base", "state.dialogs"):
            return {}
        if method == "state.letters":
            return []
        raise BridgeError(f"unknown method {method}")


def _ctx(bridge) -> Context:
    return Context(bridge=bridge, llm=None, registry=Registry(), config={"play": {}}, emit=lambda k, d: None)  # type: ignore[arg-type]


# ---------------------------------------------------------------- packet block

def test_steward_text_renders_posture_stock_problems_and_unmanaged():
    text = loop.steward_text(SAMPLE_STATUS)
    lines = text.splitlines()
    assert lines[0].startswith("posture: winter prep (expires in 36h")
    assert "Growing +0.5" in lines[0] and "forestry x1.5" in lines[0]
    assert "- wood 420/500 forestry ok, 6 designated (last run 2h ago)" in lines
    assert "- ✗ meat 40/200 hunting STALLED (3 failed runs): no safe hunting targets (last run 5h ago)" in lines
    assert "- steel 120/300 mining suspended (last run never)" in lines
    # problems first among stock rows
    stock_rows = [l for l in lines if l.startswith("- ") and ("forestry" in l or "hunting" in l or "mining" in l)]
    assert stock_rows[0].startswith("- ✗")
    assert "- hunting: no safe hunting targets for a day" in lines
    assert any(l.startswith("- Bob: Construction 1, Mining 2, Hauling 3") for l in lines)
    assert not any("Jen" in l for l in lines)  # managed pawns are not listed
    assert lines[-1].startswith("Director tools: rw_steward_stock_set")
    assert len(lines) <= 25


def test_steward_text_below_target_is_flagged_and_quiet_when_fine():
    st = {"enabled": {"scorer": True, "stock": True}, "posture": None, "pawns": [], "stock": [{"kind": "forestry", "label": "wood", "target": 500, "current": 120, "enabled": True, "failures": 0, "summary": "cut 4 trees", "last_run_hours_ago": 0.5}], "problems": []}
    text = loop.steward_text(st)
    assert "posture: none" in text
    assert "- ✗ wood 120/500 forestry below target, nothing designated: cut 4 trees (last run 30m ago)" in text
    pending = loop.steward_stock_line({"kind": "forestry", "label": "wood", "target": 500, "current": 120, "enabled": True})
    assert pending == "wood 120/500 forestry pending first run (last run never)"
    assert "Director tools" in text
    ok = dict(st, stock=[dict(st["stock"][0], current=600)])
    text2 = loop.steward_text(ok)
    assert "- wood 600/500 forestry ok (last run 30m ago)" in text2
    assert "Director tools" not in text2


def test_steward_text_truncates_and_reports_off():
    st = {"enabled": {"scorer": False, "stock": False}, "posture": None, "pawns": [{"name": f"P{i}", "managed": False, "priorities": {}} for i in range(10)],
          "stock": [{"kind": "forestry", "label": f"w{i}", "target": 10, "current": 0, "enabled": True} for i in range(15)], "problems": [f"p{i}" for i in range(9)]}
    text = loop.steward_text(st)
    assert text.startswith("steward OFF")
    assert "… 5 more jobs" in text and "… 4 more" in text
    assert len(text.splitlines()) <= 32


def test_steward_block_unavailable_when_rpc_missing():
    ctx = _ctx(FakeBridge(fail=True))
    block = loop.steward_block(ctx)
    assert block.splitlines()[0].startswith("## Steward")
    assert block.splitlines()[1] == loop.STEWARD_UNAVAILABLE == "steward: unavailable"
    assert loop.steward_text(None) == "steward: unavailable"
    assert loop.steward_text("nope") == "steward: unavailable"


def test_situation_packet_contains_steward_block_and_survives_failure():
    msg, hint = loop.situation_packet(_ctx(FakeBridge()), "scheduled check-in", [], [])
    assert "## Steward" in msg
    assert "- wood 420/500 forestry ok, 6 designated (last run 2h ago)" in msg
    assert "steward" in hint
    assert msg.index("## Steward") < msg.index("Act now.")
    msg2, _ = loop.situation_packet(_ctx(FakeBridge(fail=True)), "scheduled check-in", [], [])
    assert "## Steward" in msg2 and "steward: unavailable" in msg2
    assert msg2.endswith("Act now. End with end_turn (notes + wake plan).")


def test_steward_block_sits_after_diff_and_before_raw_numbers():
    class Bridge(FakeBridge):
        def call(self, method, **params):
            if method == "state.summary":
                return {"colonists": 1, "colonist_list": [{"name": "Jen", "id": "h1"}], "day": 3, "hour": 9}
            if method == "state.base":
                return {}
            return super().call(method, **params)

    msg, _ = loop.situation_packet(_ctx(Bridge()), "scheduled check-in", [{"kind": "steward", "text": "stock_stalled hunting"}], [])
    i_tracked, i_steward, i_events, i_numbers = msg.find("## Tracked values"), msg.index("## Steward"), msg.index("## New events"), msg.index("## Colony numbers")
    assert i_steward < i_events < i_numbers
    assert i_tracked == -1 or i_tracked < i_steward


# ---------------------------------------------------------------- roles

def _tool(name: str, source: str = "bridge") -> Tool:
    return Tool(name=name, description="", fn=lambda ctx: None, schema={}, source=source)


def test_roles_caretaker_replaces_steward_and_allow_lists():
    assert "caretaker" in roles.ROLES and "steward" not in roles.ROLES
    assert roles.CARETAKER == "caretaker"
    assert list(roles.ROLES) == ["econ", "build", "guard", "caretaker"]
    econ, build, guard, care = (roles.allow_for(r) for r in ("econ", "build", "guard", "caretaker"))
    assert econ(_tool("rw_steward_stock_set")) and econ(_tool("rw_steward_stock_add")) and econ(_tool("rw_steward_posture")) and econ(_tool("rw_steward_settings"))
    assert not build(_tool("rw_steward_stock_set")) and not build(_tool("rw_steward_posture")) and not build(_tool("rw_steward_pawn"))
    assert guard(_tool("rw_steward_posture")) and not guard(_tool("rw_steward_stock_set"))
    assert care(_tool("rw_steward_pawn")) and care(_tool("rw_steward_explain")) and not care(_tool("rw_steward_stock_set"))
    # the research queue is a write (replaces the queue unless append=true): caretaker only
    assert care(_tool("rw_steward_research")) and care(_tool("rw_ui_set_research"))
    assert not econ(_tool("rw_steward_research")) and not build(_tool("rw_steward_research")) and not guard(_tool("rw_steward_research"))
    # per-pawn override (take manual -> set -> hand back) lives in one stream
    assert care(_tool("rw_ui_set_work")) and care(_tool("rw_ui_set_work_many"))
    assert not econ(_tool("rw_ui_set_work")) and not econ(_tool("rw_ui_set_work_many"))
    assert not build(_tool("rw_ui_set_work")) and not guard(_tool("rw_ui_set_work"))
    # shared reads for everyone
    for ok in (econ, build, guard, care):
        assert ok(_tool("rw_steward_status")) and ok(_tool("rw_steward_explain")) and ok(_tool("rw_steward_stock_list"))
        assert not ok(_tool("rw_steward_enable"))
    assert "steward" in roles.ROLES["econ"]["brief"].lower() and "rw_steward_stock_set" in roles.ROLES["econ"]["brief"]
    assert "rw_steward_explain" in roles.ROLES["caretaker"]["brief"] and "rw_steward_research" in roles.ROLES["caretaker"]["brief"]
    assert "rw_ui_set_work takes the pawn" not in roles.ROLES["econ"]["brief"]
    assert "Caretaker" in roles.brief_for("econ") and "Three other streams" in roles.brief_for("caretaker")


# ---------------------------------------------------------------- config

def test_config_defaults_and_repo_yaml_have_steward_section():
    d = config_mod._DEFAULTS["steward"]
    assert d == {"enabled": True, "scorer": True, "stock": True, "research_queue_default": []}
    repo_yaml = Path(__file__).resolve().parents[2] / "config.yaml"
    cfg = config_mod.load(repo_yaml)
    st = cfg["steward"]
    assert st["enabled"] is True and st["scorer"] is True and st["stock"] is True
    assert st["research_queue_default"] == []
    assert "steward" in cfg["play"]["wake_on_kinds"]
    assert "steward" not in cfg["play"].get("critical_kinds", [])
    # a missing section falls back to the defaults
    empty = config_mod.load(Path("/nonexistent/config.yaml"))
    assert empty["steward"]["enabled"] is True


# ---------------------------------------------------------------- registry doc notes

def test_bridge_doc_notes_appended_without_breaking_calls():
    reg = Registry()
    reg.add_bridge_methods([{"method": "ui.set_work", "doc": "Set a pawn's work priority."}, {"method": "ui.designate", "doc": "Designate cells."}, {"method": "state.summary", "doc": "x"}])
    sw, dz = reg.tools["rw_ui_set_work"], reg.tools["rw_ui_designate"]
    assert sw.description.startswith("[RimBridge ui.set_work] Set a pawn's work priority.")
    assert "takes the pawn out of steward management" in sw.description
    assert "prefer rw_steward_stock_set" in dz.description and "already designate" in dz.description
    assert "steward" in sw.schema["description"] and sw.schema["additionalProperties"] is True
    assert "steward" not in reg.tools["rw_state_summary"].description
    assert set(BRIDGE_DOC_NOTES) >= {"ui.set_work", "ui.designate"}
    # idempotent re-registration
    reg.add_bridge_methods([{"method": "ui.set_work", "doc": "Set a pawn's work priority."}])
    assert reg.tools["rw_ui_set_work"].description.count("steward management") == 1

    calls = []

    class B:
        def call(self, method, **params):
            calls.append((method, params)); return {"ok": 1}

    class Ctx:
        bridge = B(); extra: dict = {}

    result, ok = reg.execute(Ctx(), "rw_ui_set_work", {"pawn": "Jen", "work": "Growing", "priority": "1"})
    assert ok and calls == [("ui.set_work", {"pawn": "Jen", "work": "Growing", "priority": 1})]
