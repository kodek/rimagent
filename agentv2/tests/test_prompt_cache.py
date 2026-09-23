from __future__ import annotations

from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo
from test_runner import Script, prompts

from agentv2.episode import Episode
from agentv2.runtime import open_runtime
from agentv2.scripted import call, code, scripted_model
from agentv2.wake import Wake

CLEARED = "[tool result cleared]"


def game_history(pairs: int, chars: int) -> list[ModelMessage]:
    history: list[ModelMessage] = [ModelRequest(parts=[UserPromptPart("## Wake trigger\nnew game started")])]
    for i in range(pairs):
        history.append(ModelResponse(parts=[ToolCallPart("run_code", {"code": f"step {i}"}, tool_call_id=f"c{i}")]))
        history.append(ModelRequest(parts=[ToolReturnPart("run_code", f"{i} " + "x" * chars, tool_call_id=f"c{i}")]))
    return history


async def director_sees(settings, bridge, bus, history: list[ModelMessage]) -> list[list[ModelMessage]]:
    seen: list[list[ModelMessage]] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "summarization" in (info.instructions or ""):
            return ModelResponse(parts=[TextPart("summary of the earlier steps")])
        seen.append(list(messages))
        return [code("1"), call("end_turn", {"notes": "x"})][len(seen) - 1]

    async with open_runtime(settings, bus, bridge, scripted_model(respond)) as rt:
        await rt.runner.load_catalog()
        rt.runner.episode = Episode(number=1, seed="rimagent-1")
        await rt.agents.director.run("situation", deps=rt.runner.director_deps(), message_history=history)
    return seen


async def test_a_step_only_adds_messages_at_the_end(settings, bridge, bus):
    first, second = await director_sees(settings, bridge, bus, game_history(3, 100))
    assert second[:len(first)] == first


async def test_compaction_waits_for_the_limit_and_then_goes_well_below_it(settings, bridge, bus):
    settings.context.keep_tool_pairs = 2
    settings.context.compact_to_tokens = 100_000
    settings.context.compact_at_tokens = 1_000_000
    history = game_history(40, 20_000)
    below = await director_sees(settings, bridge, bus, history)
    assert CLEARED not in str(below[0]) and below[1][:len(below[0])] == below[0]
    settings.context.compact_at_tokens = 150_000
    above = await director_sees(settings, bridge, bus, history)
    assert str(above[0]).count(CLEARED) >= 30
    assert above[1][:len(above[0])] == above[0]


async def test_the_report_carries_the_notebook_when_it_changes_and_the_journal_once(settings, bridge, bus):
    script = Script()
    async with open_runtime(settings, bus, bridge, scripted_model(script)) as rt:
        await rt.runner.prepare()
        await rt.runner.ensure_game()
        notebook = rt.brain.layout.notebook(rt.runner.episode.colony)
        notebook.parent.mkdir(parents=True, exist_ok=True)
        notebook.write_text("plan: rice at [100,100]", encoding="utf-8")
        reports = []
        for text in (None, None, "plan: rice at [100,100]; walls next"):
            if text:
                notebook.write_text(text, encoding="utf-8")
            script.responses = [call("end_turn", {"notes": "x"})]
            await rt.runner.step(Wake("check", False))
            reports.append(prompts(script.received[-1][-1:]))
    assert "plan: rice at [100,100]" in reports[0] and "## Journal" in reports[0]
    assert "## Your colony notebook" not in reports[1] and "## Journal" not in reports[1]
    assert "walls next" in reports[2] and "## Journal" not in reports[2]
