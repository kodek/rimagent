"""What the operator can change from the dashboard."""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .brain import OperatorLog
from .bus import Bus
from .director import DirectorSession, operator_message
from .episode import Episode
from .events import Log, Operator
from .flags import RuntimeFlags
from .game import GameSwitches
from .poller import Inbox
from .wake import Wake


@dataclass
class Controls:
    flags: RuntimeFlags
    inbox: Inbox
    director: DirectorSession
    game: GameSwitches
    operator: OperatorLog
    bus: Bus
    episode: Callable[[], Episode]

    @property
    def paused(self) -> bool:
        return self.flags.paused

    @property
    def sandbox(self) -> bool:
        return self.flags.sandbox

    @property
    def steward(self) -> bool:
        return self.flags.steward

    @property
    def no_pause(self) -> bool:
        return self.flags.danger_think_speed > 0

    async def pause(self) -> None:
        self.flags.paused = True
        self.bus.emit(Log(text="agent paused by the operator"))

    async def resume(self) -> None:
        self.flags.paused = False
        self.bus.emit(Log(text="agent resumed by the operator"))

    async def think_now(self) -> None:
        self.inbox.forced = Wake("the operator asked for a step", False)

    async def end_episode(self) -> None:
        self.inbox.end = "the operator ended the episode"
        self.director.cancel()

    async def set_no_pause(self, value: bool) -> None:
        self.flags.danger_think_speed = 1 if value else 0

    async def set_sandbox(self, value: bool) -> None:
        await self.game.apply_sandbox(self.episode(), value)
        self.inbox.forced = Wake("sandbox switched " + ("on: experiment and learn" if value else "off: play normally"), False)

    async def set_steward(self, value: bool) -> None:
        self.flags.steward = value
        await self.game.apply_steward()
        self.inbox.forced = Wake("steward switched " + ("on: direct it through rw_steward_*" if value else "off: you set priorities and designations yourself"),
                                 False)

    async def set_order(self, order_id: str, value: bool) -> Any:
        return await self.game.set_order(order_id, value)

    async def set_rally(self, rect: list[int] | None) -> Any:
        return await self.game.set_rally(rect)

    async def kill(self) -> None:
        self.flags.stop = True
        self.director.cancel()

    async def say(self, text: str) -> None:
        self.operator.record(time.strftime("%Y-%m-%d %H:%M"), text)
        self.bus.emit(Operator(text=text))
        self.inbox.operator.append(text)
        if not self.director.interrupt(operator_message(text)):
            self.inbox.forced = Wake("operator message", True)
