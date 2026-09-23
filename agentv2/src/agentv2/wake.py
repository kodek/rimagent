"""When the director wakes: watcher alerts, ledger events, game alerts, and the schedule. No I/O."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import PlaySettings
from .tools.turn import TurnEnd
from .watchers import Alert

TICKS_PER_HOUR = 2500


@dataclass(frozen=True)
class Wake:
    trigger: str
    urgent: bool


@dataclass
class WakePolicy:
    play: PlaySettings
    next_tick: int = 0
    last_end_tick: int = 0
    wake_on: set[str] = field(default_factory=set)
    seen_alerts: dict[str, int] = field(default_factory=dict)
    failed: Wake | None = None
    failures: int = 0

    def reset(self) -> None:
        self.next_tick = self.last_end_tick = self.failures = 0
        self.wake_on = set()
        self.seen_alerts = {}
        self.failed = None

    def check(self, tick: int, alerts: list[Alert], events: list[dict[str, Any]], game_alerts: list[dict[str, Any]] | None) -> Wake | None:
        """`game_alerts` is None when they were not read this time."""
        for alert in alerts:
            if alert.wake:
                return Wake(f"watcher alert: {alert.text}", True)
        recently = tick - self.last_end_tick < self.play.event_cooldown_hours * TICKS_PER_HOUR
        kinds = set(self.play.wake_on_kinds) | self.wake_on
        for e in events:
            kind = e.get("kind")
            if kind in self.play.critical_kinds:
                return Wake(f"event: {kind}: {e.get('text', '')}", True)
            if kind in kinds and not recently:
                return Wake(f"event: {kind}: {e.get('text', '')}", False)
        if game_alerts is not None and (wake := self._game_alert(tick, game_alerts)):
            return wake
        if tick >= self.next_tick:
            return Wake(f"again after a failed step: {self.failed.trigger}", self.failed.urgent) if self.failed else Wake("scheduled check-in", False)
        return None

    def schedule(self, tick: int, end: TurnEnd | None, *, urgent: bool, model_speed: int | None) -> None:
        hours = end.wake_in_hours if end and end.wake_in_hours else self.play.wake_hours
        floor = 0.5 if urgent or model_speed is not None else self.play.min_wake_hours
        self.wake_on = set(end.wake_on) if end else set()
        self.last_end_tick = tick
        self.next_tick = tick + int(max(floor, min(self.play.max_wake_hours, hours)) * TICKS_PER_HOUR)
        self.failed, self.failures = None, 0

    def retry(self, tick: int, wake: Wake) -> None:
        """A step failed: run it again soon, then less often while the failures go on."""
        self.failures += 1
        hours = min(self.play.wake_hours, self.play.failed_step_retry_hours * 2 ** (self.failures - 1))
        self.failed = self.failed or wake
        self.next_tick = tick + int(hours * TICKS_PER_HOUR)

    def _game_alert(self, tick: int, alerts: list[dict[str, Any]]) -> Wake | None:
        wake, live = None, set()
        for a in alerts:
            label, priority = str(a.get("label", "")), str(a.get("priority", ""))
            live.add(label)
            if priority not in self.play.alert_wake_priorities and "idle" not in label.lower():
                continue
            last = self.seen_alerts.get(label)
            if last is None or tick - last > self.play.alert_rewake_hours * TICKS_PER_HOUR:
                self.seen_alerts[label] = tick
                wake = wake or Wake(f"alert ({priority}): {label}", priority == "Critical")
        for label in set(self.seen_alerts) - live:
            del self.seen_alerts[label]
        return wake
