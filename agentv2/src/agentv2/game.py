"""Game switches for the runner and the operator: speed, the Steward mod and its standing orders, sandbox mode."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .bridge import Bridge, BridgeError
from .bus import Bus
from .config import StewardSettings
from .episode import Episode
from .events import Error, Status
from .flags import RuntimeFlags


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
        on, st = self.flags.steward, self.steward
        try:
            await self.bridge.call("steward.enable", {"scorer": on and st.scorer, "stock": on and st.stock})
            await self.bridge.call("steward.orders.set", {"id": "all", "enabled": on and st.orders})
        except BridgeError as e:
            self.bus.emit(Error(text=f"steward: {e} (the mod keeps its own defaults)"))
        self.bus.emit(Status(steward=on))

    async def apply_sandbox(self, episode: Episode, on: bool) -> None:
        self.flags.sandbox = episode.sandbox = on
        await self.bridge.call("game.dev_mode", {"enabled": True, "god": on})
        if on:
            await self.bridge.call("dev.unlock_all_research")
        self.bus.emit(Status(sandbox=on))

    async def set_order(self, order_id: str, enabled: bool) -> Any:
        return await self.bridge.call("steward.orders.set", {"id": order_id, "enabled": enabled})

    async def set_rally(self, rect: list[int] | None) -> Any:
        return await self.bridge.call("steward.orders.rally", {"clear": True} if rect is None else {"rect": rect})
