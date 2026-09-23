from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ThinkingPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo
from pydantic_ai.tools import ToolDefinition

from agentv2.agents import Agents, build_agents
from agentv2.brain import Brain, BrainLayout
from agentv2.catalog import parse_catalog
from agentv2.capabilities.arguments import CoerceArguments, coerce
from agentv2.deps import Deps, DirectorDeps, Episode
from agentv2.history import BrainGit, BrainTools, Scores
from agentv2.roles import DIRECTOR, IMPROVER
from agentv2.scripted import call, scripted_model
from agentv2.tools.turn import TurnEnd
from agentv2.watchers import Watchers


@dataclass
class Stack:
    agents: Agents
    deps: DirectorDeps
    brain: Brain
    seen: list[AgentInfo]
    script: list[ModelResponse]
    messages: list[list[ModelMessage]]
    watchers: Watchers


@pytest.fixture
async def stack(settings, bridge, bus):
    seen: list[AgentInfo] = []
    script: list[ModelResponse] = []
    received: list[list[ModelMessage]] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(info)
        received.append(list(messages))
        return script.pop(0)

    brain = Brain(BrainLayout(settings.brain), settings.knowledge_dir)
    async with Watchers(brain.layout.watchers_dir, bridge, bus) as watchers:
        agents = build_agents(scripted_model(respond), settings, brain, watchers, BrainTools(Scores(brain.layout.scores), BrainGit(brain.layout.root), brain.layout))
        deps = DirectorDeps(bridge=bridge, bus=bus, catalog=parse_catalog(await bridge.methods()), episode=Episode(1, "rimagent-1"), role=DIRECTOR)
        yield Stack(agents, deps, brain, seen, script, received, watchers)


async def run(stack: Stack, *responses: ModelResponse, prompt: str = "situation", history=None):
    stack.script[:] = list(responses)
    return await stack.agents.director.run(prompt, deps=stack.deps, message_history=history)


def returns(result, tool: str) -> list[ToolReturnPart]:
    return [p for m in result.all_messages() for p in getattr(m, "parts", []) if isinstance(p, ToolReturnPart) and p.tool_name == tool]


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
        call("rw_ui_draft", {"pawn": "Bob", "drafted": True}),
        call("rw_ui_build", '{"def": "Wall", "stuff": "WoodLog", "rect": "[10,10,5,5]"}'),
        call("end_turn", {"notes": "raid prep", "wake_in_hours": 2, "wake_on": ["hostile_group"]}),
    )
    assert result.output == TurnEnd(notes="raid prep", wake_in_hours=2, wake_on=["hostile_group"])
    assert ("ui.draft", {"pawn": "Bob", "drafted": True}) in game.calls
    assert ("ui.build", {"def": "Wall", "stuff": "WoodLog", "rect": [10, 10, 5, 5]}) in game.calls


async def test_bridge_error_is_a_failed_result_and_the_step_continues(stack, bus):
    queue = bus.subscribe()
    result = await run(stack, call("rw_ui_draft", {"pawn": "Nobody", "drafted": True}), call("end_turn", {"notes": "ok"}))
    assert result.output == TurnEnd(notes="ok")
    failed = returns(result, "rw_ui_draft")
    assert failed[0].outcome == "failed" and "no pawn" in failed[0].model_response_str()
    events = [queue.get_nowait() for _ in range(queue.qsize())]
    assert any(e["kind"] == "tool_result" and not e["data"]["ok"] for e in events)


async def test_tool_surface(stack):
    await run(stack, call("end_turn", {"notes": "look"}))
    names = {t.name for t in stack.seen[0].function_tools}
    assert {"rw_state_summary", "rw_ui_draft", "look", "run_code", "load_capability", "brain_write_file"} <= names
    assert {"notebook_write_memory", "journal_write_memory", "author_capability", "test_watcher", "brain_revert", "reply_to_operator"} <= names
    assert "rpc" not in names and not any(n.startswith("rw_dev_") for n in names)
    assert "rw_game_new_game" not in names
    assert {t.name for t in stack.seen[0].output_tools} == {"end_turn", "end_episode"}


async def test_sandbox_episode_shows_dev_tools(stack):
    stack.deps.episode.sandbox = True
    await run(stack, call("end_turn", {"notes": "x"}))
    assert any(t.name.startswith("rw_dev_") for t in stack.seen[0].function_tools)


async def test_brain_passes_only_read_the_game(stack, game):
    stack.script[:] = [call("run_code", {"code": "await rpc(method='ui.draft', params={'pawn': 'Bob'})"}), call("finish", {"notes": "done"})]
    deps = Deps(bridge=stack.deps.bridge, bus=stack.deps.bus, catalog=stack.deps.catalog, episode=stack.deps.episode, role=IMPROVER)
    result = await stack.agents.improver.run("improve", deps=deps)
    names = {t.name for t in stack.seen[0].function_tools}
    assert result.output.notes == "done"
    assert "rw_state_summary" in names
    assert "rw_ui_draft" not in names and "look" not in names and "reply_to_operator" not in names
    assert "ui.draft changes the game" in returns(result, "run_code")[0].model_response_str()
    assert not any(method == "ui.draft" for method, _ in game.calls)


async def test_dev_methods_need_a_sandbox_episode(stack, game):
    result = await run(stack, call("run_code", {"code": "await rpc(method='dev.unlock_all_research')"}), call("end_turn", {"notes": "x"}))
    assert "sandbox episodes" in returns(result, "run_code")[0].model_response_str()
    assert not any(method.startswith("dev.") for method, _ in game.calls)


async def test_the_speed_the_director_sets_is_tracked(stack):
    await run(stack, call("run_code", {"code": "await rpc(method='game.speed', params={'speed': 2})"}), call("end_turn", {"notes": "x"}))
    assert stack.deps.turn.model_speed == 2
    await run(stack, call("rw_game_pause", {"paused": True}), call("end_turn", {"notes": "x"}))
    assert stack.deps.turn.model_speed == 0


async def test_run_code_reaches_the_bridge_through_the_sandbox(stack):
    result = await run(stack, call("run_code", {"code": "s = await rpc(method='state.summary')\nlen(s['colonist_list'])"}), call("end_turn", {"notes": "x"}))
    returns = [p for m in result.all_messages() for p in getattr(m, "parts", []) if isinstance(p, ToolReturnPart) and p.tool_name == "run_code"]
    assert returns[0].model_response_str() == "3"


async def test_skill_catalog_and_loading(stack):
    result = await run(stack, call("load_capability", {"id": "defense-basics"}), call("end_turn", {"notes": "x"}))
    returns = [p for m in result.all_messages() for p in getattr(m, "parts", []) if isinstance(p, ToolReturnPart) and p.tool_name == "load_capability"]
    assert "# Skill: defense-basics" in returns[0].model_response_str()


async def test_notebook_is_per_colony(stack, settings):
    await run(stack, call("notebook_write_memory", {"content": "steel at [126,115]"}), call("end_turn", {"notes": "x"}))
    assert "steel at [126,115]" in stack.brain.layout.notebook(stack.deps.episode.colony).read_text()


async def test_history_carries_across_steps(stack):
    first = await run(stack, ModelResponse(parts=[ThinkingPart("think"), ToolCallPart("end_turn", {"notes": "first"})]))
    await run(stack, call("end_turn", {"notes": "second"}), prompt="next", history=first.all_messages())
    seen_prompts = [p.content for m in stack.messages[-1] for p in getattr(m, "parts", []) if p.part_kind == "user-prompt"]
    assert "situation" in seen_prompts and "next" in seen_prompts


async def test_step_budget_leaves_only_end_turn(stack, settings):
    settings.play.max_requests = 2
    stack.agents = build_agents(stack.agents.director.model, settings, stack.brain, stack.watchers,
                                BrainTools(Scores(stack.brain.layout.scores), BrainGit(stack.brain.layout.root), stack.brain.layout))
    result = await run(stack, call("rw_state_summary"), call("rw_state_summary"), call("end_turn", {"notes": "budget"}))
    assert result.output == TurnEnd(notes="budget")
    assert [len(info.function_tools) > 0 for info in stack.seen] == [True, True, False]


async def test_brain_file_tools_emit_their_events(stack, bus):
    queue = bus.subscribe()
    await run(stack, call("brain_list_directory", {"path": "skills"}), call("brain_create_directory", {"path": "skills/new-skill"}),
              call("brain_write_file", {"path": "skills/new-skill/SKILL.md", "content": "---\nname: new-skill\ndescription: d\n---\nbody\n"}),
              call("end_turn", {"notes": "x"}))
    events = [queue.get_nowait() for _ in range(queue.qsize())]
    assert all(e["data"].get("ok", True) for e in events if e["kind"] == "tool_result")
    changes = [(e["data"]["kind"], e["data"]["name"], e["data"]["action"]) for e in events if e["kind"] == "brain_change"]
    assert changes == [("skill", "skills/new-skill", "mkdir"), ("skill", "skills/new-skill/SKILL.md", "write")]
    assert "new-skill" in {s.name for s in stack.brain.skills.infos()}
