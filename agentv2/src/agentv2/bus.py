"""In-process event bus between the runner (producer) and the dashboard (consumer), on one asyncio loop.

Every event is {"seq", "t", "kind", "data"}. Persistent events go into a ring buffer (replayed to a dashboard that
reconnects) and a JSONL log. Ephemeral events (streamed thinking/text deltas) only go to live subscribers.

Kinds:
  status        game.status + {episode, seed, phase}; merged into Bus.state
  think_start   {trigger, stream, step, urgent}
  delta         ephemeral {stream, part: thinking|text, text}
  reasoning     {stream, text}                 a finished thinking part
  assistant     {stream, text}                 a finished text part
  tool_call     {stream, name, args, id}
  tool_result   {stream, name, id, ok, text, elapsed}
  think_end     {stream, notes, wake, calls, requests, elapsed, tokens}
  context       {stream, used_tokens, window_tokens, fraction}
  harness       {stream, kind, data}           a Pydantic AI Harness capability event
  ledger        one game ledger event
  watcher       {name, action|alert|error, ...}
  brain_change  {kind, name, action}
  episode_start {episode, seed, resumed}
  episode_end   {episode, score, reason, assisted, brain_sha, days}
  situation     {trigger, changes, day, hour, chars}
  operator      {text}
  reply         {text}
  log / error   {text}
"""
from __future__ import annotations

import asyncio
import collections
import json
import time
from pathlib import Path
from typing import Any


class Bus:
    def __init__(self, capacity: int = 5000, log_path: Path | None = None) -> None:
        self._events: collections.deque[dict[str, Any]] = collections.deque(maxlen=capacity)
        self._seq = 0
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self.state: dict[str, Any] = {"phase": "idle"}
        self._log = log_path.open("a", encoding="utf-8") if log_path else None

    @property
    def last_seq(self) -> int:
        return self._seq

    def emit(self, kind: str, data: dict[str, Any] | None = None, *, ephemeral: bool = False) -> dict[str, Any]:
        self._seq += 1
        event = {"seq": self._seq, "t": time.time(), "kind": kind, "data": data or {}}
        if not ephemeral:
            self._events.append(event)
            if kind == "status":
                self.state.update(event["data"])
            if self._log:
                self._log.write(json.dumps(event, default=str) + "\n")
                self._log.flush()
        for queue in list(self._subscribers):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)
        return event

    def since(self, seq: int, limit: int = 500, kinds: set[str] | None = None) -> list[dict[str, Any]]:
        out = [e for e in self._events if e["seq"] > seq and (kinds is None or e["kind"] in kinds)]
        return out[-limit:]

    def subscribe(self, maxsize: int = 2000) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)
