"""Watchers: reflexes the agent writes as brain/watchers/<name>.py and the runner executes in the Monty sandbox.

A watcher runs without the model, on each ledger poll. It cannot touch the host: no files, no imports beyond Monty's
standard subset, a time and memory limit per call. It reads the game through `rpc()` (read-only methods) and acts by
returning actions, which the runner executes and logs.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import AgentToolset, FunctionToolset
from pydantic_monty import AsyncMonty, MontyError, ResourceLimits

from .bridge import Bridge, BridgeError
from .bus import Bus
from .catalog import is_read_only
from .deps import Deps

GUIDE = '''Watchers are your reflexes: `brain/watchers/<name>.py` runs on every game-ledger poll WITHOUT you, in a sandbox
(Monty, a Python subset: no imports except json/math/re, 1 second per call). It must define

    async def watch(events, status, memo):
        ...
        return [...]

`events` are the new ledger events (dicts with kind, text, day, hour, ...); `status` is game.status; `memo` is a dict that
persists between polls (mutate it). `await rpc(method, params)` reads the game with read-only methods (state.*, map.*,
defs.*); a plain `def watch` is fine when it does not read.
Return a list of `{"type": "action", "method": "ui.draft", "params": {...}, "note": "why"}` to act through RimBridge,
or `{"type": "alert", "text": "...", "wake": True}` to wake yourself. React to events rather than polling state.
A watcher that fails is disabled until its file changes. Check one with test_watcher before you rely on it.'''

MAX_MEMORY = 64 * 1024 * 1024
_CALL = """

__out = watch(events, status, memo)
if not isinstance(__out, list):
    __out = await __out
(__out, memo)
"""


@dataclass
class Watcher:
    name: str
    source: str
    digest: str
    memo: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class WatcherError(Exception):
    pass


class Watchers:
    def __init__(self, directory: Path, bridge: Bridge, bus: Bus, timeout_s: float = 1.0) -> None:
        self.directory = directory
        self.bridge = bridge
        self.bus = bus
        self.limits: ResourceLimits = {"max_duration_secs": timeout_s, "max_memory": MAX_MEMORY}
        self.loaded: dict[str, Watcher] = {}
        self._pool: AsyncMonty | None = None

    async def __aenter__(self) -> Watchers:
        self._pool = await AsyncMonty(min_processes=1, max_processes=2, request_timeout=10).__aenter__()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._pool is not None:
            await self._pool.__aexit__(*exc)
            self._pool = None

    def scan(self) -> None:
        files = {p.stem: p for p in sorted(self.directory.glob("*.py"))}
        for name in set(self.loaded) - set(files):
            del self.loaded[name]
        for name, path in files.items():
            source = path.read_text(encoding="utf-8")
            digest = hashlib.blake2b(source.encode(), digest_size=12).hexdigest()
            current = self.loaded.get(name)
            if current is None or current.digest != digest:
                self.loaded[name] = Watcher(name, source, digest)

    async def run_all(self, events: list[dict[str, Any]], status: dict[str, Any]) -> list[dict[str, Any]]:
        """Run every healthy watcher once; execute its actions; return its alerts."""
        self.scan()
        alerts: list[dict[str, Any]] = []
        for watcher in list(self.loaded.values()):
            if watcher.error:
                continue
            try:
                out, watcher.memo = await self.evaluate(watcher, events, status, watcher.memo)
            except WatcherError as e:
                watcher.error = str(e)
                self.bus.emit("watcher", {"name": watcher.name, "error": watcher.error})
                continue
            for item in out:
                alerts += await self._apply(watcher.name, item)
        return alerts

    async def evaluate(self, watcher: Watcher, events: list[dict[str, Any]], status: dict[str, Any], memo: dict[str, Any], prints: list[str] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if self._pool is None:
            raise WatcherError("the watcher sandbox is not running")
        code = watcher.source + _CALL
        try:
            async with self._pool.checkout(script_name=f"{watcher.name}.py", limits=self.limits) as session:
                result = await session.feed_run(
                    code,
                    inputs={"events": events, "status": status, "memo": memo},
                    external_lookup={"rpc": self._rpc},
                    print_callback=(lambda _stream, text: prints.append(text)) if prints is not None else (lambda *_: None),
                )
        except MontyError as e:
            raise WatcherError(f"{type(e).__name__}: {e}") from e
        out, new_memo = result
        if not isinstance(out, list) or not all(isinstance(i, dict) for i in out):
            raise WatcherError(f"watch() must return a list of dicts, got {type(out).__name__}")
        return out, new_memo if isinstance(new_memo, dict) else {}

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if not is_read_only(method):
            raise PermissionError(f"{method} changes the game; return an action instead")
        return await self.bridge.call(method, params or {})

    async def _apply(self, name: str, item: dict[str, Any]) -> list[dict[str, Any]]:
        kind = item.get("type")
        if kind == "alert":
            self.bus.emit("watcher", {"name": name, "alert": item.get("text"), "wake": bool(item.get("wake", True))})
            return [{"watcher": name, "text": str(item.get("text", "")), "wake": bool(item.get("wake", True))}]
        if kind == "action":
            method, params = str(item.get("method", "")), item.get("params") or {}
            try:
                result, ok = await self.bridge.call(method, params), True
            except BridgeError as e:
                result, ok = str(e), False
            self.bus.emit("watcher", {"name": name, "action": method, "params": params, "note": item.get("note"), "ok": ok, "result": result})
            if item.get("wake"):
                return [{"watcher": name, "text": str(item.get("note") or method), "wake": True}]
        return []

    def errors(self) -> dict[str, str]:
        return {f"watcher {w.name}": w.error for w in self.loaded.values() if w.error}

    def listing(self) -> list[dict[str, Any]]:
        self.scan()
        return [{"name": w.name, "status": "error" if w.error else "ok", "error": w.error} for w in self.loaded.values()]


@dataclass
class WatcherTools(AbstractCapability[Deps]):
    """Lets the agent see and dry-run its watchers."""

    watchers: Watchers

    def get_instructions(self) -> str:
        return GUIDE

    def get_toolset(self) -> AgentToolset[Deps]:
        toolset = FunctionToolset[Deps](id="watchers")

        @toolset.tool
        def list_watchers(ctx: RunContext[Deps]) -> list[dict[str, Any]]:
            """List your watchers with their status (ok or error) and the error of a failed one."""
            return self.watchers.listing()

        @toolset.tool
        async def test_watcher(ctx: RunContext[Deps], name: str, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
            """Dry-run one watcher in the sandbox: its output, memo and prints. Actions are NOT executed.

            Args:
                name: The watcher file stem in brain/watchers.
                events: Ledger events to feed it (default: none).
            """
            self.watchers.scan()
            watcher = self.watchers.loaded.get(name)
            if watcher is None:
                return {"error": f"no watcher {name!r}; have {sorted(self.watchers.loaded)}"}
            prints: list[str] = []
            status = await ctx.deps.bridge.status()
            try:
                out, memo = await self.watchers.evaluate(watcher, events or [], status, {}, prints)
            except WatcherError as e:
                return {"error": str(e), "prints": prints}
            watcher.error = None
            return {"output": out, "memo": memo, "prints": prints}

        return toolset
