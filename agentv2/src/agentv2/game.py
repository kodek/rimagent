"""Game switches for the runner and the operator: speed, the Steward mod and its standing orders, sandbox mode."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .bridge import Bridge, BridgeError
from .bus import Bus
from .config import StewardSettings
from .episode import Episode
from .events import Error, Log, Status
from .flags import RuntimeFlags

ALL_ORDERS = "all"


@dataclass
class GameSwitches:
    bridge: Bridge
    bus: Bus
    steward: StewardSettings
    flags: RuntimeFlags

    async def set_speed(self, speed: int) -> None:
        try:
            if speed <= 0:
                await self.bridge.call("game.pause", {"paused": True})
            else:
                await self.bridge.call("game.speed", {"speed": speed})
                await self.bridge.call("game.pause", {"paused": False})
        except BridgeError as e:
            self.bus.emit(Error(text=f"speed {speed}: {e}"))

    async def apply_steward(self) -> None:
        """Push the steward switches and the standing orders the operator keeps off; the mod forgets them on a new game."""
        on, st, off = self.flags.steward, self.steward, self.flags.orders_off
        orders = on and st.orders and ALL_ORDERS not in off
        try:
            await self.bridge.call("steward.enable", {"scorer": on and st.scorer, "stock": on and st.stock})
            await self.bridge.call("steward.orders.set", {"id": ALL_ORDERS, "enabled": orders})
            for order_id in sorted(off - {ALL_ORDERS}) if orders else ():
                await self.bridge.call("steward.orders.set", {"id": order_id, "enabled": False})
        except BridgeError as e:
            self.bus.emit(Error(text=f"steward: {e} (the mod keeps its own defaults)"))
        self.bus.emit(Status(steward=on, orders_off=sorted(off)))

    async def queue_research(self) -> None:
        if not (self.flags.steward and self.steward.research_queue):
            return
        try:
            await self.bridge.call("steward.research", {"queue": list(self.steward.research_queue)})
            self.bus.emit(Log(text="research queue: " + ", ".join(self.steward.research_queue)))
        except BridgeError as e:
            self.bus.emit(Error(text=f"research queue: {e}"))

    async def apply_sandbox(self, episode: Episode, on: bool) -> None:
        self.flags.sandbox = episode.sandbox = on
        await self.bridge.call("game.dev_mode", {"enabled": True, "god": on})
        if on:
            await self.bridge.call("dev.unlock_all_research")
        self.bus.emit(Status(sandbox=on))

    async def set_order(self, order_id: str, enabled: bool) -> Any:
        result = await self.bridge.call("steward.orders.set", {"id": order_id, "enabled": enabled})
        off = self.flags.orders_off
        if order_id == ALL_ORDERS:
            off.clear()
        if not enabled:
            off.add(order_id)
        else:
            off.discard(order_id)
        self.bus.emit(Status(orders_off=sorted(off)))
        return result

    async def set_rally(self, rect: list[int] | None) -> Any:
        return await self.bridge.call("steward.orders.rally", {"clear": True} if rect is None else {"rect": rect})
