"""Web dashboard: live transcript (streamed thinking, tool calls, Harness events), ledger, watchers, brain, scores, base,
steward, map. It runs on the runner's event loop and reads the bus directly."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated, Any, Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from sse_starlette.sse import EventSourceResponse

from ..bridge import Bridge, BridgeError
from ..bus import Bus
from ..controls import Controls
from ..loop.store import Stage
from ..tools.vision import marked_map
from .brain_view import BrainView

PAGE = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")


class _Action(BaseModel):
    action: Literal["pause", "resume", "think", "end_episode", "kill"]

    async def apply(self, c: Controls) -> Any:
        return await {"pause": c.pause, "resume": c.resume, "think": c.think_now, "end_episode": c.end_episode, "kill": c.kill}[self.action]()


class _Switch(BaseModel):
    action: Literal["no_pause", "sandbox", "steward"]
    value: bool = False

    async def apply(self, c: Controls) -> Any:
        return await {"no_pause": c.set_no_pause, "sandbox": c.set_sandbox, "steward": c.set_steward}[self.action](self.value)


class _Order(BaseModel):
    action: Literal["order"]
    id: str
    value: bool = False

    async def apply(self, c: Controls) -> Any:
        return await c.set_order(self.id, self.value)


class _Rally(BaseModel):
    action: Literal["rally"]
    rect: list[int] | None = None

    async def apply(self, c: Controls) -> Any:
        return await c.set_rally(self.rect or None)


class _Loop(BaseModel):
    action: Literal["loop"]
    value: bool = False

    async def apply(self, c: Controls) -> Any:
        return await c.set_loop(self.value)


class _PolicyStage(BaseModel):
    action: Literal["policy_stage"]
    name: str
    stage: Stage

    async def apply(self, c: Controls) -> Any:
        return await c.set_policy_stage(self.name, self.stage)


Command = Annotated[_Action | _Switch | _Order | _Rally | _Loop | _PolicyStage, Field(discriminator="action")]
_COMMAND = TypeAdapter[Command](Command)


def create_app(bus: Bus, bridge: Bridge, brain: BrainView, controls: Controls) -> FastAPI:
    app = FastAPI(title="agentv2 dashboard", docs_url=None, redoc_url=None)

    async def call(method: str, params: dict[str, Any] | None = None, timeout: float = 20.0) -> Any:
        return await asyncio.wait_for(bridge.call(method, params or {}), timeout)

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
            game = (await asyncio.wait_for(bridge.status(), 5.0)).model_dump()
        except (BridgeError, TimeoutError):
            game = None
        ctl = {"paused": controls.paused, "no_pause": controls.no_pause, "sandbox": controls.sandbox, "steward": controls.steward}
        return {"bus": bus.state, "last_seq": bus.last_seq, "game": game, "controls": ctl}

    @app.get("/api/brain/tree")
    def api_brain_tree() -> dict[str, Any]:
        return brain.tree()

    @app.get("/api/brain/file")
    def api_brain_file(kind: str, name: str | None = None) -> dict[str, Any]:
        try:
            path = brain.file(kind, name)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if not path.is_file():
            raise HTTPException(404, f"no {kind} {name or ''}".strip())
        return {"kind": kind, "name": path.name, "text": path.read_text(encoding="utf-8")}

    @app.get("/api/git/log", response_class=PlainTextResponse)
    async def api_git_log(n: int = Query(30, ge=1, le=500)) -> str:
        return await brain.log(n)

    @app.get("/api/git/diff", response_class=PlainTextResponse)
    async def api_git_diff(sha: str) -> str:
        if not sha.isalnum() or len(sha) > 64:
            raise HTTPException(400, "bad sha")
        return await brain.diff(sha)

    @app.get("/api/scores")
    def api_scores() -> list[dict[str, Any]]:
        return brain.score_rows(100)

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

    @app.get("/api/loop")
    async def loop_view(limit: int = Query(60, ge=1, le=500)) -> dict[str, Any]:
        loop = controls.loop
        decisions = [d.model_dump(include={"id", "t", "policy", "stage", "summary", "outcome", "label", "confidence", "reason", "ms", "truth",
                                           "truth_source"}) | {"truth": "(held out)" if d.truth and loop.store.heldout(d.id) else d.truth}
                     for d in loop.store.recent(limit=limit)]
        return loop.snapshot() | {"decisions": decisions}

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
    async def api_control(req: Request) -> dict[str, Any]:
        try:
            command = _COMMAND.validate_python(await req.json())
        except ValidationError as e:
            raise HTTPException(400, f"bad control: {e.errors(include_url=False)}") from e
        try:
            result = await command.apply(controls)
        except LookupError as e:
            raise HTTPException(404, str(e)) from e
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
