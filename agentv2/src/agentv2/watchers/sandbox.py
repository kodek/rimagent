"""Run one watcher in the Monty sandbox: no host files, few imports, a time and memory limit, read-only rpc()."""
from __future__ import annotations

from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from pydantic_monty import AsyncMonty, MontyError, ResourceLimits

from ..bridge import Bridge
from ..catalog import is_read_only
from .source import Watcher

MAX_MEMORY = 64 * 1024 * 1024
_CALL = """

__out = watch(events, status, memo)
if not isinstance(__out, list):
    __out = await __out
(__out, memo)
"""


class WatcherError(Exception):
    pass


class ActionItem(BaseModel):
    type: Literal["action"]
    method: str
    params: dict[str, Any] | None = None
    note: str | None = None
    wake: bool = False


class AlertItem(BaseModel):
    type: Literal["alert"]
    text: str
    wake: bool = True


WatchItem = Annotated[ActionItem | AlertItem, Field(discriminator="type")]
_OUTPUT = TypeAdapter(list[WatchItem])


class WatcherSandbox:
    def __init__(self, bridge: Bridge, timeout_s: float = 1.0) -> None:
        self.bridge = bridge
        self.limits: ResourceLimits = {"max_duration_secs": timeout_s, "max_memory": MAX_MEMORY}
        self._pool: AsyncMonty | None = None

    async def __aenter__(self) -> Self:
        self._pool = await AsyncMonty(min_processes=1, max_processes=2, request_timeout=10).__aenter__()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._pool is not None:
            await self._pool.__aexit__(*exc)
            self._pool = None

    async def evaluate(self, watcher: Watcher, events: list[dict[str, Any]], status: dict[str, Any], memo: dict[str, Any],
                       prints: list[str] | None = None) -> tuple[list[WatchItem], dict[str, Any]]:
        if self._pool is None:
            raise WatcherError("the watcher sandbox is not running")
        try:
            async with self._pool.checkout(script_name=f"{watcher.name}.py", limits=self.limits) as session:
                out, new_memo = await session.feed_run(
                    watcher.source + _CALL,
                    inputs={"events": events, "status": status, "memo": memo},
                    external_lookup={"rpc": self._rpc},
                    print_callback=(lambda _stream, text: prints.append(text)) if prints is not None else (lambda *_: None),
                )
        except MontyError as e:
            raise WatcherError(f"{type(e).__name__}: {e}") from e
        try:
            items = _OUTPUT.validate_python(out)
        except ValidationError as e:
            raise WatcherError(f"watch() must return a list of dicts with type action or alert: {e}") from e
        return items, new_memo if isinstance(new_memo, dict) else {}

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if not is_read_only(method):
            raise PermissionError(f"{method} changes the game; return an action instead")
        return await self.bridge.call(method, params or {})
