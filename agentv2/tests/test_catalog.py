import json
from importlib import resources

from agentv2.catalog import HIDDEN, is_read_only, parse_catalog, parse_schema


def test_sketch_becomes_typed_schema():
    schema = parse_schema("{pawn, cell: [x,z], draft?: true} move a pawn to a cell")
    assert schema["properties"]["cell"]["type"] == "array"
    assert schema["properties"]["draft"]["type"] == "boolean"
    assert schema["properties"]["pawn"] == {}
    assert schema["required"] == ["pawn", "cell"]
    assert schema["additionalProperties"] is True


def test_numbers_objects_and_alternatives():
    schema = parse_schema("{speed: 0..4} set time speed")
    assert schema["properties"]["speed"]["type"] == "number"
    schema = parse_schema("{pawn, priorities: {WorkTypeDef: 0-4}} set work")
    assert schema["properties"]["priorities"]["type"] == "object"
    schema = parse_schema("{thing?|pawn?: id or name, id?: order id} release")
    assert set(schema["properties"]) == {"thing", "pawn", "id"}
    assert "required" not in schema


def test_group_alternatives_are_split():
    schema = parse_schema("{rect?: location-rect | x?, z?, center?: bool | around?: thingId} survey")
    assert {"rect", "x", "z", "center", "around"} <= set(schema["properties"])
    assert schema["properties"]["center"]["type"] == "boolean"


def test_doc_without_sketch_is_free_form():
    assert parse_schema("kill every hostile pawn") == {"type": "object", "properties": {}, "additionalProperties": True}


def test_real_catalog_parses_and_hides_lifecycle_methods():
    methods = json.loads(resources.files("agentv2").joinpath("fake_methods.json").read_text())
    catalog = parse_catalog(methods)
    names = {m.name for m in catalog}
    assert not names & HIDDEN
    assert len(catalog) == len(methods) - len(HIDDEN)
    assert all(m.schema["type"] == "object" for m in catalog)


def test_read_only_classification():
    assert is_read_only("state.summary") and is_read_only("map.find") and is_read_only("steward.orders")
    assert not is_read_only("ui.draft") and not is_read_only("steward.orders.set") and not is_read_only("engine.set")
