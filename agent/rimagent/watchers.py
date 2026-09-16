"""Run brain watchers (reflexes) every poll tick with a timeout; execute their actions through the bridge."""
from __future__ import annotations

import concurrent.futures as cf
import traceback
from typing import Any

from .context import Context

_pool = cf.ThreadPoolExecutor(max_workers=4, thread_name_prefix="watcher")


def run_all(ctx: Context, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Returns alerts (dicts with text/wake) produced this tick."""
    reg = ctx.registry
    alerts: list[dict[str, Any]] = []
    for name, fn in list(reg.watchers.items()):
        if name + ".py" in reg.watcher_errors:
            continue
        fut = _pool.submit(fn, ctx, events)
        try:
            out = fut.result(timeout=4.0)
        except cf.TimeoutError:
            reg.watcher_errors[name + ".py"] = "timed out (>4s); disabled until edited"
            ctx.emit("watcher", {"name": name, "error": "timeout"})
            continue
        except Exception:  # noqa: BLE001
            reg.watcher_errors[name + ".py"] = traceback.format_exc(limit=3)
            ctx.emit("watcher", {"name": name, "error": reg.watcher_errors[name + ".py"].splitlines()[-1]})
            continue
        for item in out or []:
            if not isinstance(item, dict):
                continue
            kind = item.get("type")
            if kind == "action":
                env = ctx.bridge.call_raw(item.get("method", ""), item.get("params") or {})
                ctx.emit("watcher", {"name": name, "action": item.get("method"), "params": item.get("params"), "note": item.get("note"), "ok": env.get("ok"), "result": env.get("result") if env.get("ok") else env.get("error")})
                if item.get("wake"):
                    alerts.append({"watcher": name, "text": item.get("note") or item.get("method"), "wake": True})
            elif kind == "alert":
                ctx.emit("watcher", {"name": name, "alert": item.get("text"), "wake": item.get("wake", True)})
                alerts.append({"watcher": name, "text": item.get("text", ""), "wake": item.get("wake", True)})
    return alerts
