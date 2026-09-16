"""Registry: schema generation, bridge tools, execute(), and hot-loading of brain tools/watchers."""
from __future__ import annotations

import os
import textwrap
import time
from typing import Optional

import pytest

from rimagent import paths
from rimagent.registry import Registry, _schema_from_signature, to_text, tool

pytestmark = pytest.mark.usefixtures("clean_brain")


# ---------------------------------------------------------------- schema

def test_schema_from_type_hints_and_defaults():
    @tool("demo", "demo tool", params={"a": "the a param", "n": "count"})
    def demo(ctx, a: str, n: int, x: float = 1.5, flag: bool = False, items: list[str] | None = None, opts: Optional[dict] = None, tags: list = [], meta: dict = {}):  # noqa: B006
        return a

    s = _schema_from_signature(demo)
    assert s["type"] == "object"
    props = s["properties"]
    assert "ctx" not in props
    assert props["a"] == {"type": "string", "description": "the a param"}
    assert props["n"] == {"type": "integer", "description": "count"}
    assert props["x"] == {"type": "number"}
    assert props["flag"] == {"type": "boolean"}
    assert props["items"] == {"type": "array"}       # Optional[list[str]] -> array
    assert props["opts"] == {"type": "object"}       # Optional[dict] -> object
    assert props["tags"] == {"type": "array"}
    assert props["meta"] == {"type": "object"}
    # only parameters without defaults are required
    assert s["required"] == ["a", "n"]


def test_schema_unannotated_defaults_to_string_and_skips_varargs():
    def f(ctx, a, *args, **kwargs):
        return a

    s = _schema_from_signature(f)
    assert list(s["properties"]) == ["a"]
    assert s["properties"]["a"] == {"type": "string"}
    assert s["required"] == ["a"]


def test_tool_decorator_defaults_to_function_name_and_docstring():
    @tool()
    def my_fn(ctx):
        """Does a thing."""

    assert my_fn._tool_name == "my_fn"
    assert my_fn._tool_desc == "Does a thing."
    assert my_fn._tool_group == "general"

    reg = Registry()
    t = reg.add(my_fn)
    spec = t.spec()
    assert spec["type"] == "function"
    assert spec["function"]["name"] == "my_fn"
    assert spec["function"]["description"] == "Does a thing."
    assert spec["function"]["parameters"]["properties"] == {}


# ---------------------------------------------------------------- bridge

def test_add_bridge_methods_creates_rw_tools_with_additional_properties():
    reg = Registry()
    reg.add_bridge_methods([
        {"method": "state.summary", "doc": "Summarize the colony state."},
        {"method": "game.speed", "doc": "Set game speed."},
    ])
    assert "rw_state_summary" in reg.tools
    t = reg.tools["rw_state_summary"]
    assert t.source == "bridge"
    assert t.group == "state"
    assert t.schema["additionalProperties"] is True
    assert t.schema["properties"] == {}
    assert "Summarize the colony state." in t.schema["description"]
    assert t.description.startswith("[RimBridge state.summary]")
    assert reg.tools["rw_game_speed"].group == "game"


def test_bridge_tool_forwards_to_ctx_bridge_call():
    reg = Registry()
    reg.add_bridge_methods([{"method": "state.summary", "doc": ""}])

    calls = []

    class FakeBridge:
        def call(self, method, **params):
            calls.append((method, params))
            return {"colonists": 3}

    class Ctx:
        bridge = FakeBridge()

    result, ok = reg.execute(Ctx(), "rw_state_summary", {"detail": "full"})
    assert ok is True
    assert result == {"colonists": 3}
    assert calls == [("state.summary", {"detail": "full"})]


def test_specs_group_filter_keeps_brain_tools_and_honours_exclude():
    reg = Registry()
    reg.add_bridge_methods([{"method": "state.summary", "doc": ""}, {"method": "game.speed", "doc": ""}])

    @tool("brainy", "b")
    def brainy(ctx):
        return 1

    reg.add(brainy, source="brain")
    names = {s["function"]["name"] for s in reg.specs(groups={"state"})}
    assert names == {"rw_state_summary", "brainy"}
    names = {s["function"]["name"] for s in reg.specs(groups={"state"}, exclude={"brainy"})}
    assert names == {"rw_state_summary"}


# ---------------------------------------------------------------- execute

def test_execute_unknown_tool_returns_error_tuple():
    reg = Registry()
    result, ok = reg.execute(None, "nope", {})
    assert ok is False
    assert "unknown tool" in result["error"]


def test_execute_tool_raising_is_captured():
    reg = Registry()

    @tool("boom", "raises")
    def boom(ctx):
        raise ValueError("kaboom")

    reg.add(boom)
    result, ok = reg.execute(None, "boom", {})
    assert ok is False
    assert result["error"] == "ValueError: kaboom"
    assert result["trace"] is None  # trace only for brain tools

    reg.add(boom, source="brain")
    result, ok = reg.execute(None, "boom", {})
    assert ok is False
    assert "kaboom" in result["trace"]


def test_execute_rejects_unknown_params_without_raising():
    reg = Registry()

    @tool("add", "adds")
    def add(ctx, a: int, b: int = 0):
        return a + b

    reg.add(add)
    result, ok = reg.execute(None, "add", {"a": 1, "zzz": 2})
    assert ok is False
    assert "unknown parameter" in result["error"]
    assert "zzz" in result["error"]
    result, ok = reg.execute(None, "add", {"a": 1, "b": 2})
    assert (result, ok) == (3, True)


def test_execute_missing_required_param_is_captured_not_raised():
    reg = Registry()

    @tool("add", "adds")
    def add(ctx, a: int):
        return a

    reg.add(add)
    result, ok = reg.execute(None, "add", {})
    assert ok is False
    assert result["error"].startswith("TypeError")


def test_to_text_truncates():
    assert to_text("abc") == "abc"
    assert to_text({"a": 1}) == '{"a": 1}'
    long = to_text("x" * 100, limit=10)
    assert long.startswith("xxxxxxxxxx\n")
    assert "truncated 90 chars" in long


# ---------------------------------------------------------------- hot load

def _write(path, src: str):
    path.write_text(textwrap.dedent(src), encoding="utf-8")


def _bump_mtime(path):
    st = path.stat()
    os.utime(path, (st.st_atime + 5, st.st_mtime + 5))


def test_hot_load_registers_brain_tool():
    f = paths.TOOLS / "hello.py"
    _write(f, '''
        from rimagent.registry import tool

        @tool("hello", "say hi", params={"name": "who"})
        def hello(ctx, name: str = "world"):
            return f"hi {name}"
    ''')
    reg = Registry()
    reg.reload_brain()
    assert "hello" in reg.tools
    t = reg.tools["hello"]
    assert t.source == "brain"
    assert t.fn._brain_file == "hello"
    assert t.schema["properties"]["name"]["description"] == "who"
    assert reg.execute(None, "hello", {"name": "Jen"}) == ("hi Jen", True)
    assert reg.load_errors == {}


def test_hot_load_syntax_error_lands_in_load_errors():
    f = paths.TOOLS / "broken.py"
    _write(f, "def x(:\n    pass\n")
    reg = Registry()
    reg.reload_brain()
    assert "broken.py" in reg.load_errors
    assert "SyntaxError" in reg.load_errors["broken.py"]
    assert not any(t.source == "brain" for t in reg.tools.values())

    # fixing the file clears the error and registers the tool
    _write(f, '''
        from rimagent.registry import tool

        @tool("fixed", "ok")
        def fixed(ctx):
            return 1
    ''')
    _bump_mtime(f)
    reg.reload_brain()
    assert "broken.py" not in reg.load_errors
    assert "fixed" in reg.tools


def test_hot_load_edit_reloads_and_delete_removes():
    f = paths.TOOLS / "counter.py"
    _write(f, '''
        from rimagent.registry import tool

        @tool("count", "v1")
        def count(ctx):
            return 1
    ''')
    reg = Registry()
    reg.reload_brain()
    assert reg.execute(None, "count", {}) == (1, True)
    assert reg.tools["count"].description == "v1"

    # same mtime -> no reload even if content differs
    st = f.stat()
    _write(f, '''
        from rimagent.registry import tool

        @tool("count", "v2")
        def count(ctx):
            return 2
    ''')
    os.utime(f, (st.st_atime, st.st_mtime))
    reg.reload_brain()
    assert reg.tools["count"].description == "v1"

    # bumped mtime -> reloaded, old tool name from this file replaced
    _bump_mtime(f)
    reg.reload_brain()
    assert reg.execute(None, "count", {}) == (2, True)
    assert reg.tools["count"].description == "v2"

    # renaming the tool inside the file drops the old name
    _write(f, '''
        from rimagent.registry import tool

        @tool("count_renamed", "v3")
        def count(ctx):
            return 3
    ''')
    _bump_mtime(f)
    reg.reload_brain()
    assert "count" not in reg.tools
    assert "count_renamed" in reg.tools

    # deleting the file removes its tools
    f.unlink()
    reg.reload_brain()
    assert "count_renamed" not in reg.tools
    assert not any(t.source == "brain" for t in reg.tools.values())


def test_hot_load_keeps_builtin_tools():
    reg = Registry()

    @tool("builtin_one", "b")
    def builtin_one(ctx):
        return 0

    reg.add(builtin_one)
    reg.reload_brain()
    assert "builtin_one" in reg.tools


# ---------------------------------------------------------------- watchers

def test_watcher_file_with_watch_function_is_registered():
    f = paths.WATCHERS / "fire.py"
    _write(f, '''
        def watch(ctx, events):
            return [{"type": "alert", "text": "fire!"}]
    ''')
    reg = Registry()
    reg.reload_brain()
    assert "fire" in reg.watchers
    assert reg.watchers["fire"](None, []) == [{"type": "alert", "text": "fire!"}]
    assert reg.watcher_errors == {}


def test_watcher_file_without_watch_function_is_an_error():
    f = paths.WATCHERS / "nowatch.py"
    _write(f, "x = 1\n")
    reg = Registry()
    reg.reload_brain()
    assert "nowatch" not in reg.watchers
    assert reg.watcher_errors["nowatch.py"] == "no watch(ctx, events) function"


def test_watcher_syntax_error_and_delete():
    f = paths.WATCHERS / "bad.py"
    _write(f, "def watch(ctx, events)\n    return []\n")
    reg = Registry()
    reg.reload_brain()
    assert "bad.py" in reg.watcher_errors
    assert "SyntaxError" in reg.watcher_errors["bad.py"]
    assert "bad" not in reg.watchers

    _write(f, "def watch(ctx, events):\n    return []\n")
    _bump_mtime(f)
    reg.reload_brain()
    assert "bad.py" not in reg.watcher_errors
    assert "bad" in reg.watchers

    f.unlink()
    reg.reload_brain()
    assert "bad" not in reg.watchers
