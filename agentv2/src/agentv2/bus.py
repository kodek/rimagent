"""In-process event bus between the producers (runner, runs, watchers) and the consumers (dashboard, sinks), on one
asyncio loop. Every event is {"seq", "t", "kind", "data"}; the kinds are the models in events.py. Persistent events
go into a ring buffer (replayed to a dashboard that reconnects) and to the sinks; ephemeral ones only to live subscribers."""
from __future__ import annotations

import asyncio
import collections
import json
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from .events import Event, Status

Sink = Callable[[dict[str, Any]], None]


class Bus:
    def __init__(self, capacity: int = 5000, sinks: Sequence[Sink] = ()) -> None:
        self._events: collections.deque[dict[str, Any]] = collections.deque(maxlen=capacity)
        self._seq = 0
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._sinks = list(sinks)
        self.state: dict[str, Any] = {"phase": "idle"}

    @property
    def last_seq(self) -> int:
        return self._seq

    def emit(self, event: Event, *, stream: str | None = None) -> dict[str, Any]:
        self._seq += 1
        data = {"stream": stream, **event.payload()} if stream else event.payload()
        record = {"seq": self._seq, "t": time.time(), "kind": event.KIND, "data": data}
        if not event.EPHEMERAL:
            self._events.append(record)
            if isinstance(event, Status):
                self.state.update(data)
            for sink in self._sinks:
                sink(record)
        for queue in list(self._subscribers):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(record)
        return record

    def since(self, seq: int, limit: int = 500, kinds: set[str] | None = None) -> list[dict[str, Any]]:
        out = [e for e in self._events if e["seq"] > seq and (kinds is None or e["kind"] in kinds)]
        return out[-limit:]

    def subscribe(self, maxsize: int = 2000) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)


class JsonlLog:
    """A sink that appends every persistent event to a JSONL file."""

    def __init__(self, path: Path) -> None:
        self._file = path.open("a", encoding="utf-8")

    def __call__(self, record: dict[str, Any]) -> None:
        self._file.write(json.dumps(record, default=str) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()
