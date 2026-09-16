"""In-process event bus."""
from __future__ import annotations

import threading
import time

from rimagent import paths
from rimagent.bus import Bus


def test_emit_assigns_seq_and_since_filters():
    bus = Bus(log_file=False)
    assert bus.last_seq == 0
    e1 = bus.emit("log", {"text": "a"})
    e2 = bus.emit("tool_call", {"name": "x"})
    e3 = bus.emit("log")
    assert (e1["seq"], e2["seq"], e3["seq"]) == (1, 2, 3)
    assert e3["data"] == {}
    assert all(isinstance(e["t"], float) for e in (e1, e2, e3))
    assert bus.last_seq == 3

    assert [e["seq"] for e in bus.since(0)] == [1, 2, 3]
    assert [e["seq"] for e in bus.since(1)] == [2, 3]
    assert bus.since(3) == []
    assert [e["seq"] for e in bus.since(0, kinds={"log"})] == [1, 3]
    assert [e["seq"] for e in bus.since(0, kinds={"nothing"})] == []
    assert [e["seq"] for e in bus.since(0, limit=2)] == [2, 3]


def test_status_updates_state():
    bus = Bus(log_file=False)
    assert bus.state == {"phase": "idle"}
    bus.emit("status", {"phase": "thinking", "episode": 2})
    assert bus.state == {"phase": "thinking", "episode": 2}
    bus.emit("log", {"phase": "nope"})
    assert bus.state["phase"] == "thinking"
    bus.emit("status", {"phase": "playing"})
    assert bus.state == {"phase": "playing", "episode": 2}


def test_wait_returns_on_new_event():
    bus = Bus(log_file=False)
    bus.emit("log", {"text": "old"})
    # already-newer events return immediately
    got = bus.wait(0, timeout=5)
    assert [e["seq"] for e in got] == [1]

    def later():
        time.sleep(0.05)
        bus.emit("log", {"text": "new"})

    t = threading.Thread(target=later)
    t0 = time.monotonic()
    t.start()
    got = bus.wait(1, timeout=5)
    t.join()
    assert time.monotonic() - t0 < 2
    assert [e["seq"] for e in got] == [2]
    assert got[0]["data"]["text"] == "new"


def test_wait_times_out_with_no_events():
    bus = Bus(log_file=False)
    t0 = time.monotonic()
    assert bus.wait(0, timeout=0.05) == []
    assert time.monotonic() - t0 >= 0.04


def test_capacity_ring_drops_oldest():
    bus = Bus(capacity=3, log_file=False)
    for i in range(5):
        bus.emit("log", {"i": i})
    assert [e["seq"] for e in bus.since(0)] == [3, 4, 5]
    assert bus.last_seq == 5


def test_subscribers_receive_events_and_errors_are_swallowed():
    bus = Bus(log_file=False)
    seen = []
    bus.subscribe(seen.append)
    bus.subscribe(lambda ev: 1 / 0)
    bus.emit("log", {"text": "x"})
    assert len(seen) == 1 and seen[0]["kind"] == "log"


def test_log_file_written_under_runs():
    # The file is named by wall-clock second, so it may coincide with the module-level BUS's file (append mode).
    bus = Bus(log_file=True)
    marker = f"hello-{time.time_ns()}"
    bus.emit("log", {"text": marker})
    files = list(paths.RUNS.glob("run-*.jsonl"))
    assert files and all(str(f).startswith(str(paths.ROOT)) for f in files)
    assert any(marker in f.read_text(encoding="utf-8") for f in files)
