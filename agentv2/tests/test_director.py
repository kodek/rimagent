from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import pytest
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessage, ModelResponse, RetryPromptPart, ThinkingPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo
from pydantic_ai.tools import ToolDefinition

from agentv2.capabilities.arguments import CoerceArguments, coerce
from agentv2.deps import DirectorDeps
from agentv2.episode import Episode
from agentv2.roles import IMPROVER
from agentv2.runtime import Runtime, open_runtime
from agentv2.scripted import call, code, scripted_model
from agentv2.tools.turn import TurnEnd
from agentv2.wake import Wake


@dataclass
class Stack:
    rt: Runtime
    deps: DirectorDeps
    seen: list[AgentInfo]
    script: list[ModelResponse]
    messages: list[list[ModelMessage]]


@asynccontextmanager
async def open_stack(settings, bridge, bus) -> AsyncIterator[Stack]:
    seen: list[AgentInfo] = []
    script: list[ModelResponse] = []
    received: list[list[ModelMessage]] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(info)
        received.append(list(messages))
        return script.pop(0)

    async with open_runtime(settings, bus, bridge, scripted_model(respond)) as rt:
        await rt.runner.load_catalog()
        rt.runner.episode = Episode(number=1, seed="rimagent-1")
        yield Stack(rt, rt.runner.director_deps(), seen, script, received)


@pytest.fixture
async def stack(settings, bridge, bus):
    async with open_stack(settings, bridge, bus) as s:
        yield s


async def run(stack: Stack, *responses: ModelResponse, prompt: str = "situation", history=None):
    stack.script[:] = list(responses)
    return await stack.rt.agents.director.run(prompt, deps=stack.deps, message_history=history)


def returns(result, tool: str) -> list[ToolReturnPart]:
    return [p for m in result.all_messages() for p in getattr(m, "parts", []) if isinstance(p, ToolReturnPart) and p.tool_name == tool]


def code_errors(result) -> str:
    return "\n".join(p.model_response() for m in result.all_messages() for p in getattr(m, "parts", [])
                     if isinstance(p, RetryPromptPart) and p.tool_name == "run_code")


def run_code_description(info: AgentInfo) -> str:
    return next(t.description or "" for t in info.function_tools if t.name == "run_code")


def test_coerce_undoes_json_strings():
    assert coerce({"rect": "[1, 2, 3, 4]", "fill": "true", "n": "80", "name": "Bob"}) == {"rect": [1, 2, 3, 4], "fill": True, "n": 80, "name": "Bob"}


async def test_coerce_arguments_decodes_twice_and_keeps_string_fields():
    tool = ToolDefinition(name="t", parameters_json_schema={"type": "object", "properties": {"text": {"type": "string"},
                                                                                            "note": {"anyOf": [{"type": "string"}, {"type": "null"}]}}})
    args = json.dumps(json.dumps({"text": "123", "note": "true", "rect": "[1, 2]"}))
    out = await CoerceArguments().before_tool_validate(None, call=ToolCallPart("t", args), tool_def=tool, args=args)  # type: ignore[arg-type]
    assert out == {"text": "123", "note": "true", "rect": [1, 2]}


async def test_step_calls_bridge_and_ends_with_a_wake_plan(stack, game):
    result = await run(
        stack,
        code("await rw_ui_draft(pawn='Bob', drafted=True)\nawait rw_ui_build(def_='Wall', stuff='WoodLog', rect=[10, 10, 5, 5])"),
        call("end_turn", {"notes": "raid prep", "wake_in_hours": 2, "wake_on": ["hostile_group"]}),
    )
    assert result.output == TurnEnd(notes="raid prep", wake_in_hours=2, wake_on=["hostile_group"])
    assert ("ui.draft", {"pawn": "Bob", "drafted": True}) in game.calls
    assert ("ui.build", {"def": "Wall", "stuff": "WoodLog", "rect": [10, 10, 5, 5]}) in game.calls


async def test_bridge_error_is_a_failed_result_and_the_step_continues(stack, bus):
    queue = bus.subscribe()
    result = await run(stack, code("await rw_ui_draft(pawn='Nobody', drafted=True)"), call("end_turn", {"notes": "ok"}))
    assert result.output == TurnEnd(notes="ok")
    assert "no pawn" in code_errors(result)
    events = [queue.get_nowait() for _ in range(queue.qsize())]
    assert any(e["kind"] == "tool_result" and e["data"]["name"] == "rw_ui_draft" and not e["data"]["ok"] for e in events)


async def test_calls_from_code_are_reported_under_their_run_code_call(stack, bus):
    await run(stack, code("s = await rw_state_summary()\nawait rw_ui_draft(pawn='Bob', drafted=True)"), call("end_turn", {"notes": "x"}))
    events = [e["data"] for e in bus.since(0, kinds={"tool_call", "tool_result"})]
    run_code_id = next(e["id"] for e in events if e["name"] == "run_code")
    nested = [(e["name"], "args" in e, e.get("ok")) for e in events if e.get("parent") == run_code_id]
    assert nested == [("rw_state_summary", True, None), ("rw_state_summary", False, True), ("rw_ui_draft", True, None), ("rw_ui_draft", False, True)]


async def test_code_gets_whole_results_and_the_model_gets_them_cut(stack):
    trees = "await rw_map_find(kind='tree', limit=500)"
    result = await run(stack, code(f"len(({trees})['things'])"), code(trees), call("end_turn", {"notes": "x"}))
    whole, cut = returns(result, "run_code")
    assert whole.model_response_str() == "500"
    assert "Tool output too large" in cut.model_response_str()


async def test_tool_surface(stack):
    await run(stack, call("end_turn", {"notes": "look"}))
    info = stack.seen[0]
    assert {t.name for t in info.function_tools} == {"run_code", "load_capability", "author_capability"}
    functions = run_code_description(info)
    for name in ("rw_state_summary", "rw_ui_draft", "look", "brain_write_file", "notebook_write_memory", "journal_write_memory",
                 "test_watcher", "brain_revert", "reply_to_operator"):
        assert f"def {name}(" in functions
    for name in ("rpc", "rw_dev_", "rw_game_new_game", "search_conversation_history"):
        assert f"def {name}" not in functions
    assert "async def rw_ui_build(*, def_: Any" in functions and "All tool functions are async" in functions
    assert {t.name for t in info.output_tools} == {"end_turn", "end_episode"}


async def test_sandbox_episode_shows_dev_tools(stack):
    stack.deps.episode.sandbox = True
    await run(stack, call("end_turn", {"notes": "x"}))
    assert "def rw_dev_" in run_code_description(stack.seen[0])


async def test_brain_passes_only_read_the_game(stack, game):
    stack.script[:] = [code("await rw_ui_draft(pawn='Bob', drafted=True)"), call("finish", {"notes": "done"})]
    result = await stack.rt.agents.improver.run("improve", deps=stack.rt.runner.deps(IMPROVER))
    functions = run_code_description(stack.seen[0])
    assert result.output.notes == "done"
    assert "def rw_state_summary(" in functions and "def search_conversation_history(" in functions
    assert "def rw_ui_draft(" not in functions and "def look(" not in functions and "def reply_to_operator(" not in functions
    assert "rw_ui_draft" in code_errors(result)
    assert not any(method == "ui.draft" for method, _ in game.calls)


async def test_dev_methods_need_a_sandbox_episode(stack, game):
    result = await run(stack, code("await rw_dev_unlock_all_research()"), call("end_turn", {"notes": "x"}))
    assert "rw_dev_unlock_all_research" in code_errors(result)
    assert not any(method.startswith("dev.") for method, _ in game.calls)


async def test_the_speed_the_director_sets_is_tracked(stack):
    await run(stack, code("await rw_game_speed(speed=2)"), call("end_turn", {"notes": "x"}))
    assert stack.deps.turn.model_speed == 2
    await run(stack, code("await rw_game_pause(paused=True)"), call("end_turn", {"notes": "x"}))
    assert stack.deps.turn.model_speed == 0


async def test_code_gathers_game_changes(stack, game):
    drafts = "rw_ui_draft(pawn='Bob', drafted=True), rw_ui_draft(pawn='Ann', drafted=True)"
    result = await run(stack, code(f"import asyncio\n[r['pawn'] for r in await asyncio.gather({drafts})]"), call("end_turn", {"notes": "x"}))
    assert returns(result, "run_code")[0].model_response_str() == '["Bob","Ann"]'
    assert [p["pawn"] for method, p in game.calls if method == "ui.draft"] in (["Bob", "Ann"], ["Ann", "Bob"])


async def test_code_composes_bridge_calls(stack):
    result = await run(stack, code("s = await rw_state_summary()\nlen(s['colonist_list'])"), call("end_turn", {"notes": "x"}))
    assert returns(result, "run_code")[0].model_response_str() == "3"


async def test_look_gives_the_model_the_image(stack):
    result = await run(stack, code("await look()"), call("end_turn", {"notes": "x"}))
    content = returns(result, "run_code")[0].content
    assert isinstance(content, list) and isinstance(content[1], BinaryContent)
    assert "Bed1" in str(content[0]) and content[1].media_type == "image/png"


async def test_skill_catalog_and_loading(stack):
    result = await run(stack, call("load_capability", {"id": "defense-basics"}), call("end_turn", {"notes": "x"}))
    assert "# Skill: defense-basics" in returns(result, "load_capability")[0].model_response_str()


async def test_a_broken_authored_capability_is_left_out(stack, bus):
    stack.rt.brain.creation.store.write("broken", "from dataclasses import dataclass\nfrom pydantic_ai.capabilities import AbstractCapability\n"
                                                  "from pydantic_ai.exceptions import UserError\n@dataclass\nclass Broken(AbstractCapability):\n"
                                                  "    async def before_run(self, ctx):\n        raise UserError('broken on purpose')\n")
    stack.script[:] = [call("end_turn", {"notes": "played anyway"})]
    outcome = await stack.rt.director.step("situation", stack.deps, Wake("x", False))
    assert outcome.notes == "played anyway"
    assert any("authored capability broke the run" in e["data"].get("text", "") for e in bus.since(0, kinds={"error"}))


async def test_notebook_is_per_colony(stack):
    await run(stack, code("await notebook_write_memory(content='steel at [126,115]')"), call("end_turn", {"notes": "x"}))
    assert "steel at [126,115]" in stack.rt.brain.layout.notebook(stack.deps.episode.colony).read_text()


async def test_history_carries_across_steps(stack):
    first = await run(stack, ModelResponse(parts=[ThinkingPart("think"), ToolCallPart("end_turn", {"notes": "first"})]))
    await run(stack, call("end_turn", {"notes": "second"}), prompt="next", history=first.all_messages())
    seen_prompts = [p.content for m in stack.messages[-1] for p in getattr(m, "parts", []) if p.part_kind == "user-prompt"]
    assert "situation" in seen_prompts and "next" in seen_prompts


async def test_step_budget_leaves_only_end_turn(settings, bridge, bus):
    settings.play.max_requests = 2
    async with open_stack(settings, bridge, bus) as stack:
        summary = code("await rw_state_summary()")
        result = await run(stack, summary, summary, call("end_turn", {"notes": "budget"}))
        assert result.output == TurnEnd(notes="budget")
        assert [len(info.function_tools) > 0 for info in stack.seen] == [True, True, False]


async def test_brain_file_tools_emit_their_events(stack, bus):
    queue = bus.subscribe()
    skill = "---\\nname: new-skill\\ndescription: d\\n---\\nbody\\n"
    await run(stack, code("await brain_list_directory(path='skills')\n"
                          "await brain_create_directory(path='skills/new-skill')\n"
                          f"await brain_write_file(path='skills/new-skill/SKILL.md', content='{skill}')"),
              call("end_turn", {"notes": "x"}))
    events = [queue.get_nowait() for _ in range(queue.qsize())]
    assert all(e["data"].get("ok", True) for e in events if e["kind"] == "tool_result")
    changes = [(e["data"]["kind"], e["data"]["name"], e["data"]["action"]) for e in events if e["kind"] == "brain_change"]
    assert changes == [("skill", "skills/new-skill", "mkdir"), ("skill", "skills/new-skill/SKILL.md", "write")]
    assert "new-skill" in {s.name for s in stack.rt.brain.skills.infos()}
