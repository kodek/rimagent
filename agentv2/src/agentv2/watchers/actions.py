"""Carry out what a watcher returned: call RimBridge for an action, raise an alert for the runner, log both."""
from __future__ import annotations

from dataclasses import dataclass

from ..bridge import Bridge, BridgeError
from ..bus import Bus
from ..events import WatcherAction, WatcherAlert
from ..policy import WATCHER_ACTIONS
from .sandbox import ActionItem, WatchItem


@dataclass(frozen=True)
class Alert:
    watcher: str
    text: str
    wake: bool


class WatcherActions:
    def __init__(self, bridge: Bridge, bus: Bus) -> None:
        self.bridge = bridge
        self.bus = bus

    async def apply(self, name: str, item: WatchItem) -> Alert | None:
        if not isinstance(item, ActionItem):
            self.bus.emit(WatcherAlert(name=name, alert=item.text, wake=item.wake))
            return Alert(name, item.text, item.wake)
        params = item.params or {}
        if refusal := WATCHER_ACTIONS.refusal(item.method):
            result, ok = f"refused: {refusal}", False
        else:
            try:
                result, ok = await self.bridge.call(item.method, params), True
            except BridgeError as e:
                result, ok = str(e), False
        self.bus.emit(WatcherAction(name=name, action=item.method, params=params, note=item.note, ok=ok, result=result))
        return Alert(name, item.note or item.method, True) if item.wake else None
