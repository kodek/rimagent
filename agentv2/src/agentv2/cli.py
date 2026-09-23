"""agentv2 command line."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import webbrowser
from typing import Any

from . import config
from .bridge import Bridge
from .bus import Bus
from .model import build_model


def _printer(event: dict[str, Any]) -> None:
    kind, data = event["kind"], event["data"]
    if kind == "tool_call":
        print(f"→ [{data.get('stream')}] {data['name']} {json.dumps(data['args'])[:300]}")
    elif kind == "tool_result":
        print(f"← [{data.get('stream')}] {data['name']} {'ok' if data['ok'] else 'FAILED'} {data['text'][:300]}")
    elif kind == "reasoning":
        print(f"[thinking] {data['text'][:400].replace(chr(10), ' ')}…")
    elif kind in ("assistant", "log", "error", "think_start", "think_end", "episode_start", "episode_end", "watcher", "brain_change", "reply", "harness"):
        print(f"[{kind}] {json.dumps(data, default=str)[:600]}")


async def _play(args: argparse.Namespace, fake: bool) -> None:
    from .dashboard.app import create_app, serve
    from .fakegame import FakeGame
    from .runner import Runner

    settings = config.load()
    if args.max_days:
        settings.play.max_days = args.max_days
    if args.seeds:
        settings.play.seeds = args.seeds.split(",")
    settings.runs.mkdir(parents=True, exist_ok=True)
    bus = Bus(log_path=settings.runs / f"events-{time.strftime('%Y%m%d-%H%M%S')}.jsonl")
    tasks: list[asyncio.Task[None]] = []
    if fake:
        game = FakeGame()
        bridge = Bridge("http://fakegame", transport=game.transport())
        tasks.append(asyncio.create_task(game.run_clock(), name="fake-clock"))
    else:
        bridge = Bridge(settings.bridge.url, settings.bridge.timeout_s)
    runner = Runner(settings, bus, bridge, build_model(settings.llm))
    if args.verbose:
        queue = bus.subscribe(maxsize=10_000)

        async def pump() -> None:
            while True:
                _printer(await queue.get())

        tasks.append(asyncio.create_task(pump(), name="printer"))
    if not args.no_dashboard:
        host, port = settings.dashboard.host, settings.dashboard.port
        tasks.append(asyncio.create_task(serve(create_app(runner), port, host), name="dashboard"))
        url = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}"
        print(f"dashboard: {url} (listening on {host}:{port})")
        if settings.dashboard.open_browser:
            asyncio.get_running_loop().call_later(2, webbrowser.open, url)
    try:
        await runner.run()
    finally:
        for task in tasks:
            task.cancel()
        await bridge.aclose()


async def _tools(_: argparse.Namespace) -> None:
    from pydantic_ai.messages import ModelResponse
    from pydantic_ai.models.function import AgentInfo

    from .agents import build_agents
    from .brain import Brain
    from .catalog import parse_catalog
    from .deps import Deps, Episode
    from .fakegame import FakeGame
    from .history import BrainGit, BrainTools, Scores
    from .scripted import call, scripted_model
    from .watchers import Watchers

    settings = config.load()
    game = FakeGame()
    bridge = Bridge("http://fakegame", transport=game.transport())
    bus = Bus()
    brain = Brain(settings.brain, settings.knowledge_dir)
    seen: list[AgentInfo] = []

    def respond(_: list[Any], info: AgentInfo) -> ModelResponse:
        seen.append(info)
        return call("end_turn", {"notes": "listing tools"})

    async with Watchers(brain.watchers_dir, bridge, bus) as watchers:
        agents = build_agents(scripted_model(respond), settings, brain, watchers, BrainTools(Scores(brain.scores), BrainGit(brain.root)))
        caps = brain.run_capabilities()
        deps = Deps(bridge=bridge, bus=bus, settings=settings, catalog=parse_catalog(await bridge.methods()), episode=Episode(1, "tools"))
        await agents.director.run("list", deps=deps, capabilities=[*caps.skills, *caps.authored])
    for tool in sorted(seen[0].function_tools, key=lambda t: t.name):
        print(f"{tool.name:34s} {(tool.description or '').splitlines()[0][:100]}")
    print(f"\n{len(seen[0].function_tools)} tools; output tools: {', '.join(t.name for t in seen[0].output_tools)}")
    for name, error in caps.errors.items():
        print(f"brain problem: {name}: {error}")


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
        p.add_argument("-v", "--verbose", action="store_true")
    sub.add_parser("tools", help="list the director's tools")
    llm = sub.add_parser("llm", help="test the model endpoint")
    llm.add_argument("prompt")
    args = parser.parse_args(argv)
    try:
        match args.cmd:
            case "play" | "fake":
                asyncio.run(_play(args, fake=args.cmd == "fake"))
            case "tools":
                asyncio.run(_tools(args))
            case "llm":
                asyncio.run(_llm(args))
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()
