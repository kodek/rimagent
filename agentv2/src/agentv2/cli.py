"""agentv2 command line."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import webbrowser
from typing import Any

from . import config, events
from .bridge import Bridge
from .bus import Bus, JsonlLog
from .loop.fakejev import FakeJev
from .loop.jev import JevClient
from .model import build_model

_PRINTED = {e.KIND for e in (events.Assistant, events.Log, events.Error, events.ThinkStart, events.ThinkEnd, events.EpisodeStart, events.EpisodeEnd,
                             events.WatcherAlert, events.BrainChange, events.Reply, events.Harness)}


def _printer(event: dict[str, Any]) -> None:
    kind, data = event["kind"], event["data"]
    if kind == events.ToolCall.KIND:
        print(f"{'    ' if data.get('parent') else ''}→ [{data.get('stream')}] {data['name']} {json.dumps(data['args'])[:300]}")
    elif kind == events.ToolResult.KIND:
        print(f"{'    ' if data.get('parent') else ''}← [{data.get('stream')}] {data['name']} {'ok' if data['ok'] else 'FAILED'} {data['text'][:300]}")
    elif kind == events.Reasoning.KIND:
        print(f"[thinking] {data['text'][:400].replace(chr(10), ' ')}…")
    elif kind in _PRINTED:
        print(f"[{kind}] {json.dumps(data, default=str)[:600]}")


async def _play(args: argparse.Namespace, fake: bool) -> None:
    from .dashboard.app import create_app, serve
    from .fakegame import FakeGame
    from .runtime import open_runtime

    settings = config.load()
    if args.max_days:
        settings.play.max_days = args.max_days
    if args.seeds:
        settings.play.seeds = args.seeds.split(",")
    settings.runs.mkdir(parents=True, exist_ok=True)
    log = JsonlLog(settings.runs / f"events-{time.strftime('%Y%m%d-%H%M%S')}.jsonl")
    bus = Bus(sinks=[log, _printer] if args.verbose else [log])
    tasks: list[asyncio.Task[None]] = []
    if fake:
        game = FakeGame()
        bridge = Bridge("http://fakegame", transport=game.transport())
        tasks.append(asyncio.create_task(game.run_clock(), name="fake-clock"))
    else:
        bridge = Bridge(settings.bridge.url, settings.bridge.timeout_s)
    jev = FakeJev() if fake else _jev(settings)
    try:
        async with open_runtime(settings, bus, bridge, build_model(settings.llm), jev) as rt:
            if not args.no_dashboard:
                host, port = settings.dashboard.host, settings.dashboard.port
                tasks.append(asyncio.create_task(serve(create_app(bus, bridge, rt.brain_view, rt.controls), port, host), name="dashboard"))
                url = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}"
                print(f"dashboard: {url} (listening on {host}:{port})")
                if settings.dashboard.open_browser:
                    asyncio.get_running_loop().call_later(2, webbrowser.open, url)
            rt.runner.start_new_game = args.new_game
            await rt.runner.run()
    finally:
        for task in tasks:
            task.cancel()
        await bridge.aclose()
        if isinstance(jev, JevClient):
            await jev.aclose()
        log.close()


def _jev(settings: config.Settings) -> JevClient | None:
    if not settings.jev.api_key:
        print("fast loop off: no Jev key (jev.api_key in config.local.yaml, or TYPESAFE_API_KEY)")
        return None
    return JevClient(settings.jev)


async def _tools(_: argparse.Namespace) -> None:
    from pydantic_ai.messages import ModelResponse
    from pydantic_ai.models.function import AgentInfo

    from .episode import Episode
    from .fakegame import FakeGame
    from .runtime import open_runtime
    from .scripted import call, scripted_model

    settings = config.load()
    bridge = Bridge("http://fakegame", transport=FakeGame().transport())
    seen: list[AgentInfo] = []

    def respond(_: list[Any], info: AgentInfo) -> ModelResponse:
        seen.append(info)
        return call("end_turn", {"notes": "listing tools"})

    async with open_runtime(settings, Bus(), bridge, scripted_model(respond)) as rt:
        await rt.runner.load_catalog()
        rt.runner.episode = Episode(number=1, seed="tools")
        await rt.agents.director.run("list", deps=rt.runner.director_deps())
        problems = rt.brain.problems()
    for tool in sorted(seen[0].function_tools, key=lambda t: t.name):
        print(f"{tool.name:34s} {(tool.description or '').splitlines()[0][:100]}")
    run_code = next(t.description or "" for t in seen[0].function_tools if t.name == "run_code")
    functions = [line for line in run_code.splitlines() if line.startswith(("def ", "async def "))]
    for line in functions:
        print(f"  {line[:130]}")
    print(f"\n{len(seen[0].function_tools)} tools, {len(functions)} functions in run_code; "
          f"output tools: {', '.join(t.name for t in seen[0].output_tools)}")
    for name, error in problems.items():
        print(f"brain problem: {name}: {error}")


async def _think(args: argparse.Namespace) -> None:
    """One director step against the running game, then the game waits paused."""
    from .runtime import open_runtime
    from .wake import Wake

    settings = config.load()
    bridge = Bridge(settings.bridge.url, settings.bridge.timeout_s)
    jev = _jev(settings)
    try:
        async with open_runtime(settings, Bus(sinks=[_printer]), bridge, build_model(settings.llm), jev) as rt:
            await rt.runner.prepare()
            if not (await bridge.status()).playing:
                print("no game is playing: start one with `agentv2 play`")
                return
            await rt.runner.ensure_game()
            outcome = await rt.runner.step(Wake(args.trigger, args.urgent))
            await rt.runner.game.set_speed(0)
            print(f"\nnotes: {outcome.notes}\nwake: {outcome.end.model_dump() if outcome.end else outcome.episode_end or outcome.error}\nthe game is paused")
    finally:
        await bridge.aclose()
        if jev:
            await jev.aclose()


async def _seed(args: argparse.Namespace) -> None:
    from .knowledge import seed

    settings = config.load()
    await seed(settings.knowledge_dir, refresh=args.refresh, limit=args.limit, index_only=args.index_only)


async def _llm(args: argparse.Namespace) -> None:
    from pydantic_ai import Agent
    from pydantic_ai.messages import ThinkingPart

    settings = config.load()
    started = time.monotonic()
    result = await Agent(build_model(settings.llm)).run(args.prompt)
    for message in result.all_messages():
        for part in getattr(message, "parts", []):
            if isinstance(part, ThinkingPart):
                print("thinking:", part.content[:500])
    print("answer:", result.output)
    print("usage:", result.usage, f"elapsed: {time.monotonic() - started:.1f}s")


def main(argv: list[str] | None = None) -> None:
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
    parser = argparse.ArgumentParser(prog="agentv2")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, help_text in (("play", "play RimWorld through RimBridge, unattended"), ("fake", "play the in-process fake game (no RimWorld)")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--max-days", type=int)
        p.add_argument("--seeds")
        p.add_argument("--no-dashboard", action="store_true")
        p.add_argument("--new-game", action="store_true", help="start a new game; the stored episode stays without a score")
        p.add_argument("-v", "--verbose", action="store_true")
    sub.add_parser("tools", help="list the director's tools")
    think = sub.add_parser("think", help="one director step against the running game (for debugging), then pause the game")
    think.add_argument("--trigger", default="the operator asked for one step")
    think.add_argument("--urgent", action="store_true")
    seed = sub.add_parser("seed", help="download the RimWorld wiki into ../knowledge and index it")
    seed.add_argument("--refresh", action="store_true", help="download the pages that are already there too")
    seed.add_argument("--limit", type=int, help="only the first N articles (for a quick check)")
    seed.add_argument("--index-only", action="store_true", help="only rebuild the search index")
    llm = sub.add_parser("llm", help="test the model endpoint")
    llm.add_argument("prompt")
    args = parser.parse_args(argv)
    try:
        match args.cmd:
            case "play" | "fake":
                asyncio.run(_play(args, fake=args.cmd == "fake"))
            case "tools":
                asyncio.run(_tools(args))
            case "think":
                asyncio.run(_think(args))
            case "seed":
                asyncio.run(_seed(args))
            case "llm":
                asyncio.run(_llm(args))
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()
