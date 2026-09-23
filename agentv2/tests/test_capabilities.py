from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic_ai.messages import ToolReturnPart
from test_runner import Script

from agentv2.runtime import open_runtime
from agentv2.scripted import call, code, scripted_model


@pytest.fixture
async def director(settings, bridge, bus):
    script = Script()
    async with open_runtime(settings, bus, bridge, scripted_model(script)) as rt:
        await rt.runner.prepare()
        await rt.runner.ensure_game()

        async def run(snippet: str) -> Any:
            script.responses = [code(snippet), call("end_turn", {"notes": "x"})]
            result = await rt.agents.director.run("go", deps=rt.runner.director_deps())
            part = next(p for m in result.all_messages() for p in getattr(m, "parts", []) if isinstance(p, ToolReturnPart) and p.tool_name == "run_code")
            assert part.outcome != "failed", part.model_response_str()
            return json.loads(part.model_response_str())

        yield rt, run


async def test_the_seed_brain_has_the_v1_tools_as_authored_capabilities(director):
    rt, _ = director
    assert [r.name for r in rt.brain.creation.store.list_all() if r.status == "active" and not r.last_error] == ["colony_reports", "production", "construction"]


async def test_ensure_bills_adds_standard_bills_and_removes_duplicates(director, game):
    _, run = director
    game.things = [{"id": "Campfire1", "def": "Campfire", "kind": "building"}, {"id": "Spot1", "def": "ButcherSpot", "kind": "building"},
                   {"id": "Boar1", "def": "Corpse_Boar", "kind": "corpse", "of": "Boar"}]
    game.bills = {"Spot1": [{"recipe": "ButcherCorpseFlesh"}, {"recipe": "ButcherCorpseFlesh"}]}
    status = await run("await my_production_status()")
    assert status["duplicates"] == [{"id": "Spot1", "recipe": "ButcherCorpseFlesh"}] and status["corpses"]["animal"] == 1
    planned = await run("await my_ensure_bills(dry_run=True)")
    assert planned["added"] == [{"id": "Campfire1", "recipe": "CookMealSimple", "mode": "TargetCount", "count": 10}] and len(game.bills["Spot1"]) == 2
    await run("await my_ensure_bills()")
    assert [b["recipe"] for b in game.bills["Campfire1"]] == ["CookMealSimple"] and len(game.bills["Spot1"]) == 1
    assert (await run("await my_ensure_bills()")) == {"added": [], "removed": [], "dry_run": False}


async def test_the_reports_read_the_game(director, game):
    _, run = director
    game.hostiles = [{"id": "Human9", "name": "Raider", "faction": "Pirates", "weapon": "Club", "dist_home": 25}]
    game.things = [{"id": "Sandbags1", "def": "Sandbags", "kind": "building"}] + [
        {"id": f"Rice{i}", "def": "Plant_Rice", "growth": 0.5, "harvestable": False} for i in range(10)]
    game.colonists[1]["mood"] = 30
    defense = await run("await my_defense_readiness()")
    assert defense["verdict"][0].startswith("HOSTILES CLOSING") and defense["unarmed"] == ["Ann"] and defense["defenses"] == {"Sandbags": 1}
    morale = await run("await my_morale_report()")
    assert "ALERT" in morale[1] and morale[0]["worst_thoughts"] == ["Slept outside -4", "Ate without table -3"]
    farm = await run("await my_farm_report()")
    assert farm["crops"] == [{"crop": "Plant_Rice", "plants": 10, "mean_growth": 0.5, "ready": 0, "grow_days": 5.0, "days_to_ripe": 2.5}]
    assert farm["notes"] == ["30 of 40 growing cells are empty"]
    assert (await run("await my_storage_report()"))["notes"] == ["NO STOCKPILES"]
    assert "planned" in await run("await my_build_report()")
    room = await run("await my_room(x=10, z=10, w=6, h=5, beds=2)")
    assert room["door"] == [13, 10]
    assert ("ui.build_many", {"ops": [
        {"def": "Wall", "rect": [10, 10, 6, 5], "stuff": "WoodLog", "dry_run": True}, {"def": "Door", "at": [13, 10], "stuff": "WoodLog", "dry_run": True},
        {"def": "Bed", "at": [11, 11], "rot": "E", "stuff": "WoodLog", "dry_run": True}, {"def": "Bed", "at": [11, 13], "rot": "E", "stuff": "WoodLog", "dry_run": True}]}) in game.calls
