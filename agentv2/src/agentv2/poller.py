"""The poller reads the game status and new ledger events all the time, also while the director thinks, and runs the
watchers. What it finds waits in the inbox for the next step; urgent items go to the step that runs now."""
from __future__ import annotations

import asyncio
import time
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .bridge import Bridge, BridgeError, BridgeUnreachable, GameStatus
from .bus import Bus
from .config import Settings
from .episode import Episode
from .events import Error, Ledger, Status
from .wake import Wake
from .watchers import Alert, Watchers


@dataclass
class Inbox:
    events: list[dict[str, Any]] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    operator: list[str] = field(default_factory=list)
    forced: Wake | None = None
    end: str | None = None

    def take(self) -> tuple[list[dict[str, Any]], list[Alert]]:
        events, alerts = self.events, self.alerts
        self.events, self.alerts = [], []
        return events, alerts

    def take_forced(self) -> Wake | None:
        forced, self.forced = self.forced, None
        return forced

    def clear(self) -> None:
        self.events, self.alerts, self.operator, self.forced = [], [], [], None


class LedgerPoller:
    def __init__(self, bridge: Bridge, bus: Bus, watchers: Watchers, inbox: Inbox, settings: Settings,
                 on_urgent: Callable[[list[str]], Awaitable[None]], on_menu: Callable[[], None],
                 on_day: Callable[[GameStatus], Awaitable[None]]) -> None:
        self.bridge = bridge
        self.bus = bus
        self.watchers = watchers
        self.inbox = inbox
        self.poll_s = settings.watchers.poll_s
        self.critical_kinds = set(settings.play.critical_kinds)
        self.on_urgent = on_urgent
        self.on_menu = on_menu
        self.on_day = on_day
        self.lost_contact = False
        self.status = GameStatus()
        self.last_seq = 0
        self._status_emitted = 0.0
        self._watched = 0.0

    async def run(self, episode: Callable[[], Episode], stopped: Callable[[], bool]) -> None:
        while not stopped():
            try:
                await self.poll_once(episode())
            except BridgeUnreachable:
                self.lost_contact = True
            except BridgeError:
                pass
            except Exception as e:  # noqa: BLE001 - the poller reports and keeps polling; the main loop owns recovery
                self.bus.emit(Error(text=f"poller: {e}\n{traceback.format_exc(limit=6)}"))
            await asyncio.sleep(0.5)

    async def poll_once(self, episode: Episode) -> None:
        st = self.status = await self.bridge.status()
        if time.monotonic() - self._status_emitted >= 1.0:
            self._status_emitted = time.monotonic()
            self.bus.emit(Status.model_validate(st.model_dump(exclude_unset=True)))
        if st.state == "menu":
            self.on_menu()
        if not st.playing or not episode.seed:
            return
        episode.assisted |= st.assisted
        data = await self.bridge.events(self.last_seq, 500)
        events: list[dict[str, Any]] = data.get("events") or []
        if events:
            self.last_seq = int(data.get("last_seq", self.last_seq))
            for e in events:
                self.bus.emit(Ledger.model_validate(e))
            before = (episode.deaths, episode.raids)
            episode.tally(events)
            if (episode.deaths, episode.raids) != before:
                self.bus.emit(Status(deaths=episode.deaths, raids=episode.raids))
            self.inbox.events += events
        await self.on_day(st)
        alerts: list[Alert] = []
        if events or time.monotonic() - self._watched >= self.poll_s:
            self._watched = time.monotonic()
            alerts = await self.watchers.run_all(events, st.model_dump())
            self.inbox.alerts += alerts
        urgent = [f"{e.get('kind')}: {e.get('text', '')}" for e in events if e.get("kind") in self.critical_kinds]
        urgent += [f"watcher {a.watcher}: {a.text}" for a in alerts if a.wake]
        if urgent:
            await self.on_urgent(urgent)
