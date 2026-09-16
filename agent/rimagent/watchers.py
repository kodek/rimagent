"""Run brain watchers (reflexes) every poll tick with a timeout; execute their actions through the bridge."""
from __future__ import annotations

import concurrent.futures as cf
import traceback
from typing import Any

from .context import Context

_pool = cf.ThreadPoolExecutor(max_workers=4, thread_name_prefix="watcher")

# Brain watchers that the standing orders (mod/Source/Steward/Orders) replaced: stem -> order id. While that order is on,
# run_all skips the watcher, because its ui.draft/goto/order/designate calls record manual touches that make the order
# leave those very pawns/things alone (Order_Combat finds no eligible fighter after hostile_draft moved everyone, Order_Rescue
# treats rescue_downed's patient as hands-off, ...). config steward.orders.superseded_watchers overrides the mapping.
SUPERSEDED_WATCHERS: dict[str, str] = {
    "hostile_draft": "combat",
    "undraft_after_fight": "combat",
    "fire_alert": "fire",
    "rescue_downed": "rescue",
    "unforbid_drops_watcher": "unforbid",
    "rotting_corpses": "corpses",
    "food_policy_watcher": "policies",
    "build_stall": "blueprints",
}


def superseded_mapping(cfg_value: Any) -> dict[str, str]:
    """config steward.orders.superseded_watchers: a {stem: order id} dict, a list of stems (order id looked up in the
    default table, else "orders"), or missing/None for the default table. An empty dict/list disables the feature."""
    if cfg_value is None:
        return dict(SUPERSEDED_WATCHERS)
    if isinstance(cfg_value, dict):
        return {str(k).removesuffix(".py"): str(v) for k, v in cfg_value.items() if k and v}
    if isinstance(cfg_value, (list, tuple, set)):
        return {str(k).removesuffix(".py"): SUPERSEDED_WATCHERS.get(str(k).removesuffix(".py"), "orders") for k in cfg_value if k}
    return dict(SUPERSEDED_WATCHERS)


def superseded_now(mapping: dict[str, str], *, orders_supported: bool, orders_on: bool, orders_off: set[str] | None = None) -> dict[str, str]:
    """The subset of `mapping` to skip right now: nothing when the mod has no steward.orders or all orders are off, and a
    watcher whose order is individually off keeps running (it covers again)."""
    if not orders_supported or not orders_on:
        return {}
    off = set(orders_off or ())
    return {k: v for k, v in mapping.items() if v not in off}


def run_all(ctx: Context, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Returns alerts (dicts with text/wake) produced this tick."""
    reg = ctx.registry
    alerts: list[dict[str, Any]] = []
    for name, fn in list(reg.watchers.items()):
        if name + ".py" in reg.watcher_errors or name in getattr(reg, "watcher_superseded", {}):
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
