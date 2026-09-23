from __future__ import annotations

from agentv2.config import PlaySettings
from agentv2.tools.turn import TurnEnd
from agentv2.wake import TICKS_PER_HOUR, Wake, WakePolicy
from agentv2.watchers import Alert

HOUR = TICKS_PER_HOUR


def policy() -> WakePolicy:
    return WakePolicy(PlaySettings(wake_hours=12, min_wake_hours=4, max_wake_hours=48, event_cooldown_hours=3, alert_rewake_hours=24))


def test_a_waking_watcher_alert_comes_first():
    wake = policy().check(0, [Alert("raid", "quiet", False), Alert("raid", "RAID", True)], [{"kind": "colonist_downed", "text": "Bob"}], None)
    assert wake == Wake("watcher alert: RAID", True)


def test_critical_events_are_urgent_and_other_kinds_respect_the_cooldown():
    p = policy()
    p.schedule(10 * HOUR, TurnEnd(notes="", wake_in_hours=24), urgent=False, model_speed=None)
    assert p.check(11 * HOUR, [], [{"kind": "letter", "text": "trader"}], None) is None
    assert p.check(11 * HOUR, [], [{"kind": "colonist_downed", "text": "Bob"}], None) == Wake("event: colonist_downed: Bob", True)
    assert p.check(14 * HOUR, [], [{"kind": "letter", "text": "trader"}], None) == Wake("event: letter: trader", False)


def test_end_turn_adds_wake_kinds_and_the_schedule_is_clamped():
    p = policy()
    p.schedule(0, TurnEnd(notes="", wake_in_hours=100, wake_on=["day"]), urgent=False, model_speed=None)
    assert p.next_tick == 48 * HOUR
    assert p.check(5 * HOUR, [], [{"kind": "day", "text": "day 2"}], None) == Wake("event: day: day 2", False)
    p.schedule(0, TurnEnd(notes="", wake_in_hours=0.1), urgent=True, model_speed=None)
    assert p.next_tick == int(0.5 * HOUR)
    p.schedule(0, None, urgent=False, model_speed=None)
    assert p.next_tick == 12 * HOUR and p.wake_on == set()


def test_a_game_alert_wakes_once_until_it_clears_or_the_rewake_time_passes():
    p = policy()
    p.next_tick = 10**9
    alerts = [{"label": "Colonist needs rescue", "priority": "Critical"}, {"label": "Low food", "priority": "Medium"}]
    assert p.check(0, [], [], alerts) == Wake("alert (Critical): Colonist needs rescue", True)
    assert p.check(HOUR, [], [], alerts) is None
    assert p.check(26 * HOUR, [], [], alerts) == Wake("alert (Critical): Colonist needs rescue", True)
    assert p.check(27 * HOUR, [], [], []) is None
    assert p.check(28 * HOUR, [], [], alerts) is not None


def test_the_schedule_wakes_when_due():
    p = policy()
    p.schedule(0, None, urgent=False, model_speed=None)
    assert p.check(11 * HOUR, [], [], None) is None
    assert p.check(12 * HOUR, [], [], None) == Wake("scheduled check-in", False)


def test_a_failed_step_runs_again_soon_and_backs_off():
    p = policy()
    p.play.failed_step_retry_hours = 1
    raid = Wake("event: hostile_group: raiders", True)
    p.retry(0, raid)
    assert p.next_tick == HOUR
    assert p.check(HOUR, [], [], None) == Wake("again after a failed step: event: hostile_group: raiders", True)
    p.retry(HOUR, Wake("again after a failed step: event: hostile_group: raiders", True))
    assert p.next_tick == 3 * HOUR and p.failed == raid
    for _ in range(5):
        p.retry(0, raid)
    assert p.next_tick == 12 * HOUR
    p.schedule(0, None, urgent=False, model_speed=None)
    assert p.failed is None and p.check(12 * HOUR, [], [], None) == Wake("scheduled check-in", False)
