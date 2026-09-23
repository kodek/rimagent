"""Web dashboard: live transcript (streamed thinking, tool calls, Harness events), ledger, watchers, brain, scores, base,
steward, map. It runs on the runner's event loop and reads the bus directly."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ..bridge import BridgeError
from ..runner import Controls, Runner
from ..tools.vision import marked_map

PAGE = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
_ACTIONS = {"pause": "pause", "resume": "resume", "think": "think_now", "end_episode": "end_episode", "no_pause": "set_no_pause",
            "sandbox": "set_sandbox", "steward": "set_steward", "order": "set_order", "rally": "set_rally", "kill": "kill"}
_BOOL_ACTIONS = {"no_pause", "sandbox", "steward"}


class ControlRequest(BaseModel):
    action: str
    value: bool | None = None
    id: str | None = None
    rect: list[int] | None = None


def _chars(path: Path) -> int | None:
    return len(path.read_text(encoding="utf-8")) if path.is_file() else None


def _unsafe(name: str | None) -> bool:
    return not name or "/" in name or "\\" in name or ".." in name or name.startswith(".")


def create_app(runner: Runner) -> FastAPI:
    app = FastAPI(title="agentv2 dashboard", docs_url=None, redoc_url=None)
    bus, bridge, brain, controls = runner.bus, runner.bridge, runner.brain, Controls(runner)

    async def call(method: str, params: dict[str, Any] | None = None, timeout: float = 20.0) -> Any:
        return await asyncio.wait_for(bridge.call(method, params or {}), timeout)

    def brain_file(kind: str, name: str | None) -> Path:
        colony = runner.episode.colony
        fixed = {"doctrine": brain.doctrine, "notebook": brain.memory_file("notebook", colony),
                 "journal": brain.memory_file("journal", colony), "operator": brain.operator_log}
        if kind in fixed:
            return fixed[kind]
        if _unsafe(name):
            raise HTTPException(400, "bad name")
        paths = {"skill": brain.skills_dir / str(name) / "SKILL.md", "watcher": brain.watchers_dir / f"{name}.py",
                 "capability": brain.capabilities_dir / f"{name}.py"}
        if kind not in paths:
            raise HTTPException(400, f"unknown kind {kind!r}")
        return paths[kind]

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return PAGE

    @app.get("/api/events")
    def api_events(since: int = 0, kinds: str | None = None, limit: int = Query(500, ge=1, le=5000)) -> list[dict[str, Any]]:
        wanted = {k.strip() for k in kinds.split(",") if k.strip()} if kinds else None
        return bus.since(since, limit=limit, kinds=wanted)

    @app.get("/stream")
    async def stream(request: Request, since: int = 0) -> EventSourceResponse:
        last_id = request.headers.get("last-event-id")
        if last_id and last_id.isdigit():
            since = int(last_id)
        queue = bus.subscribe()

        async def events():
            seq = since
            try:
                for event in bus.since(seq, limit=5000):
                    seq = event["seq"]
                    yield {"id": str(seq), "data": json.dumps(event, default=str)}
                while not await request.is_disconnected():
                    try:
                        event = await asyncio.wait_for(queue.get(), 5.0)
                    except TimeoutError:
                        continue
                    if event["seq"] > seq:
                        seq = event["seq"]
                        yield {"id": str(seq), "data": json.dumps(event, default=str)}
            finally:
                bus.unsubscribe(queue)

        return EventSourceResponse(events(), ping=15)

    @app.get("/api/state")
    async def api_state() -> dict[str, Any]:
        try:
            game = await asyncio.wait_for(bridge.status(), 5.0)
        except (BridgeError, TimeoutError):
            game = None
        ctl = {"paused": controls.paused, "no_pause": controls.no_pause, "sandbox": controls.sandbox, "steward": controls.steward}
        return {"bus": bus.state, "last_seq": bus.last_seq, "game": game, "controls": ctl}

    @app.get("/api/brain/tree")
    def api_brain_tree() -> dict[str, Any]:
        colony = runner.episode.colony
        return {
            "skills": [{"name": s.name, "description": s.description, "chars": s.chars, "error": s.error} for s in brain.skills()],
            "watchers": runner.watchers.listing(),
            "capabilities": brain.authored(),
            "colony": colony if runner.episode.seed else None,
            "memory": {"doctrine": _chars(brain.doctrine), "notebook": _chars(brain.memory_file("notebook", colony)),
                       "journal": _chars(brain.memory_file("journal", colony)), "operator": _chars(brain.operator_log)},
        }

    @app.get("/api/brain/file")
    def api_brain_file(kind: str, name: str | None = None) -> dict[str, Any]:
        path = brain_file(kind, name)
        if not path.is_file():
            raise HTTPException(404, f"no {kind} {name or ''}".strip())
        return {"kind": kind, "name": path.name, "text": path.read_text(encoding="utf-8")}

    @app.get("/api/git/log", response_class=PlainTextResponse)
    async def api_git_log(n: int = Query(30, ge=1, le=500)) -> str:
        return await runner.git.log(n)

    @app.get("/api/git/diff", response_class=PlainTextResponse)
    async def api_git_diff(sha: str) -> str:
        if not sha.isalnum() or len(sha) > 64:
            raise HTTPException(400, "bad sha")
        return await runner.git.diff(sha)

    @app.get("/api/scores")
    def api_scores() -> list[dict[str, Any]]:
        return runner.scores.history(100)

    @app.get("/api/ledger")
    async def api_ledger(since: int = 0) -> dict[str, Any]:
        try:
            return await asyncio.wait_for(bridge.events(since), 10.0)
        except (BridgeError, TimeoutError) as e:
            return {"events": [], "error": str(e)}

    @app.get("/api/ascii")
    async def ascii_view(x: int | None = None, z: int | None = None, w: int = 80, h: int = 50, layer: str = "all", mode: str = "view",
                         around: str | None = None, roof: bool = False) -> Any:
        params: dict[str, Any] = {"w": w, "h": h}
        if mode == "detail":
            params |= {"roof": roof} | ({"around": around} if around else {})
        else:
            params["layer"] = layer
        if x is not None and z is not None and not around:
            params |= {"x": x, "z": z}
        return await _bridge_json(call("map.detail" if mode == "detail" else "map.view", params))

    @app.get("/api/base")
    async def base_view(verbose: bool = False) -> Any:
        return await _bridge_json(call("state.base", {"verbose": verbose}))

    @app.get("/api/anchors")
    async def anchors_view() -> Any:
        return await _bridge_json(call("anchor.list"))

    @app.get("/api/overview")
    async def overview(blocks: int = 60) -> Any:
        return await _bridge_json(call("map.overview", {"blocks": blocks}))

    @app.get("/api/steward")
    async def steward_view() -> Any:
        try:
            status = await call("steward.status", timeout=15.0)
        except (BridgeError, TimeoutError) as e:
            return JSONResponse({"error": str(e), "unavailable": True}, status_code=503)
        if isinstance(status, dict) and "research" not in status:
            status["research"] = await _optional(call("steward.research", timeout=10.0))
        if isinstance(status, dict) and isinstance(status.get("orders"), list):
            rows = await _optional(call("steward.orders", timeout=10.0))
            if isinstance(rows, list) and rows:
                status["orders"] = rows
        return status

    @app.get("/screenshot.png")
    async def screenshot(x: int | None = None, z: int | None = None, w: float = 80) -> Response:
        try:
            png = await asyncio.wait_for(bridge.screenshot(x, z, w), 35.0)
        except (BridgeError, TimeoutError) as e:
            return JSONResponse({"error": str(e)}, status_code=503)
        return Response(content=png, media_type="image/png", headers={"Cache-Control": "no-store"})

    @app.get("/screenshot_marked.png")
    async def screenshot_marked(x: int | None = None, z: int | None = None, w: float = 80) -> Response:
        try:
            seen = await asyncio.wait_for(marked_map(bridge, x, z, w), 40.0)
        except (BridgeError, TimeoutError) as e:
            return JSONResponse({"error": str(e)}, status_code=503)
        return Response(content=seen.image, media_type="image/png", headers={"Cache-Control": "no-store"})

    @app.post("/api/say")
    async def say(req: Request) -> Any:
        text = str((await req.json()).get("text", "")).strip()
        if not text:
            return JSONResponse({"ok": False, "error": "empty"}, status_code=400)
        await controls.say(text)
        return {"ok": True}

    @app.post("/api/control")
    async def api_control(req: ControlRequest) -> dict[str, Any]:
        method = _ACTIONS.get(req.action)
        if method is None:
            raise HTTPException(400, f"unknown action {req.action!r}")
        fn = getattr(controls, method)
        try:
            if req.action == "order":
                if not req.id:
                    raise HTTPException(400, "order needs an id")
                result = await fn(req.id, bool(req.value))
            elif req.action == "rally":
                result = await fn(list(req.rect) if req.rect else None)
            else:
                result = await (fn(bool(req.value)) if req.action in _BOOL_ACTIONS else fn())
        except BridgeError as e:
            return {"ok": False, "error": str(e), "paused": controls.paused}
        return {"ok": True, "result": result, "paused": controls.paused, "no_pause": controls.no_pause}

    return app


async def _bridge_json(awaitable: Any) -> Any:
    try:
        return await awaitable
    except (BridgeError, TimeoutError) as e:
        return JSONResponse({"error": str(e)}, status_code=503)


async def _optional(awaitable: Any) -> Any:
    try:
        return await awaitable
    except (BridgeError, TimeoutError):
        return None


async def serve(app: FastAPI, port: int, host: str = "127.0.0.1") -> None:
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False, lifespan="off"))
    await server.serve()
