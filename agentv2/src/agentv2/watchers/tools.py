"""Lets the agent see and dry-run its watchers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic_ai import RunContext, ToolFailed
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import AgentToolset, FunctionToolset

from ..deps import Deps
from . import Watchers

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


@dataclass
class WatcherTools(AbstractCapability[Deps]):
    watchers: Watchers

    def get_instructions(self) -> str:
        return GUIDE

    def get_toolset(self) -> AgentToolset[Deps]:
        toolset = FunctionToolset[Deps](id="watchers")
        watchers = self.watchers

        @toolset.tool_plain
        def list_watchers() -> list[dict[str, Any]]:
            """List your watchers with their status (ok or error) and the error of a failed one."""
            return watchers.listing()

        @toolset.tool
        async def test_watcher(ctx: RunContext[Deps], name: str, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
            """Dry-run one watcher in the sandbox: its output, memo and prints. Actions are NOT executed.

            Args:
                name: The watcher file stem in brain/watchers.
                events: Ledger events to feed it (default: none).
            """
            status = await ctx.deps.bridge.status()
            try:
                return await watchers.dry_run(name, events or [], status)
            except LookupError as e:
                raise ToolFailed(str(e)) from e

        return toolset
