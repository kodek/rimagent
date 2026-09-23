"""Watchers: reflexes the agent writes as brain/watchers/<name>.py. They run without the model, on each ledger poll,
in the Monty sandbox; they read the game through rpc() and act by returning actions, which the runner carries out."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Self

from ..bridge import Bridge
from ..bus import Bus
from ..events import WatcherFailed
from .actions import Alert, WatcherActions
from .sandbox import WatcherError, WatcherSandbox
from .source import Watcher, WatcherRepository

__all__ = ["Alert", "Watcher", "WatcherError", "Watchers"]


class Watchers:
    def __init__(self, directory: Path, bridge: Bridge, bus: Bus, timeout_s: float = 1.0) -> None:
        self.repository = WatcherRepository(directory)
        self.sandbox = WatcherSandbox(bridge, timeout_s)
        self.actions = WatcherActions(bridge, bus)
        self.bus = bus

    async def __aenter__(self) -> Self:
        await self.sandbox.__aenter__()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.sandbox.__aexit__(*exc)

    async def run_all(self, events: list[dict[str, Any]], status: dict[str, Any]) -> list[Alert]:
        """Run every healthy watcher once; carry out its actions; return its alerts."""
        alerts: list[Alert] = []
        for watcher in self.repository.scan():
            if watcher.error:
                continue
            try:
                items, watcher.memo = await self.sandbox.evaluate(watcher, events, status, watcher.memo)
            except WatcherError as e:
                watcher.error = str(e)
                self.bus.emit(WatcherFailed(name=watcher.name, error=watcher.error))
                continue
            for item in items:
                if alert := await self.actions.apply(watcher.name, item):
                    alerts.append(alert)
        return alerts

    async def dry_run(self, name: str, events: list[dict[str, Any]], status: dict[str, Any]) -> dict[str, Any]:
        """Evaluate one watcher with an empty memo and carry out nothing; a clean run re-enables a failed watcher."""
        self.repository.scan()
        watcher = self.repository.loaded.get(name)
        if watcher is None:
            raise LookupError(f"no watcher {name!r}; have {sorted(self.repository.loaded)}")
        prints: list[str] = []
        try:
            items, memo = await self.sandbox.evaluate(watcher, events, status, {}, prints)
        except WatcherError as e:
            return {"error": str(e), "prints": prints}
        watcher.error = None
        return {"output": [i.model_dump(exclude_none=True) for i in items], "memo": memo, "prints": prints}

    def errors(self) -> dict[str, str]:
        return {f"watcher {w.name}": w.error for w in self.repository.loaded.values() if w.error}

    def listing(self) -> list[dict[str, Any]]:
        return [{"name": w.name, "status": "error" if w.error else "ok", "error": w.error} for w in self.repository.scan()]
