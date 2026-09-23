"""`rpc`: generic bridge access that exists only inside CodeMode's `run_code` (the Monty sandbox)."""
from __future__ import annotations

from typing import Any

from pydantic_ai import RunContext, ToolFailed
from pydantic_ai.toolsets import FunctionToolset

from ..bridge import BridgeError
from ..catalog import HIDDEN, is_read_only
from ..deps import Deps

CODE_MODE = {"code_mode": True}

sandbox = FunctionToolset[Deps](id="sandbox")


@sandbox.tool(metadata=CODE_MODE)
async def rpc(ctx: RunContext[Deps], method: str, params: dict[str, Any] | None = None) -> Any:
    """Call any RimBridge method by its dotted name, e.g. rpc(method='map.find', params={'kind': 'tree', 'limit': 200}).

    Args:
        method: Dotted method name, as in the rw_* tool descriptions.
        params: Method parameters.
    """
    if method in HIDDEN:
        raise ToolFailed(f"{method} is reserved for the runner")
    if method.startswith("dev.") and not ctx.deps.episode.sandbox:
        raise ToolFailed("dev.* methods exist only in sandbox episodes")
    if ctx.deps.stream != "play" and not is_read_only(method):
        raise ToolFailed(f"{method} changes the game; this pass may only read it")
    try:
        return await ctx.deps.bridge.call(method, params or {})
    except BridgeError as e:
        raise ToolFailed(str(e)) from e
