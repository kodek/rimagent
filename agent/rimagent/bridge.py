"""HTTP client for the RimBridge mod."""
from __future__ import annotations

import time
from typing import Any

import httpx

from .config import CONFIG


class BridgeError(Exception):
    pass


class Bridge:
    def __init__(self, url: str | None = None, timeout: float = 60.0):
        self.url = (url or CONFIG["bridge"]["url"]).rstrip("/")
        self._client = httpx.Client(base_url=self.url, timeout=timeout)

    # ---- low level ----
    def call(self, method: str, timeout_ms: int | None = None, **params: Any) -> Any:
        payload: dict[str, Any] = {"method": method, "params": params}
        if timeout_ms:
            payload["timeout_ms"] = timeout_ms
        try:
            r = self._client.post("/rpc", json=payload, timeout=(timeout_ms or 60000) / 1000 + 5)
        except httpx.HTTPError as e:
            raise BridgeError(f"bridge unreachable: {e}") from e
        try:
            data = r.json()
        except ValueError as e:
            raise BridgeError(f"bad response: {r.text[:200]}") from e
        if not data.get("ok"):
            raise BridgeError(data.get("error", "unknown error"))
        return data.get("result")

    def call_raw(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return the raw envelope (ok/result/error) without raising."""
        try:
            r = self._client.post("/rpc", json={"method": method, "params": params or {}}, timeout=95)
            return r.json()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"bridge unreachable: {e}"}

    def health(self) -> dict[str, Any] | None:
        try:
            r = self._client.get("/health", timeout=3)
            return r.json()
        except Exception:  # noqa: BLE001
            return None

    def methods(self) -> list[dict[str, str]]:
        r = self._client.get("/methods", timeout=10)
        return r.json()["result"]

    def events(self, since: int, limit: int = 500) -> dict[str, Any]:
        r = self._client.get("/events", params={"since": since, "limit": limit}, timeout=10)
        return r.json()["result"]

    def screenshot(self, x: int | None = None, z: int | None = None, w: float = 60, width_px: int = 1024, height_px: int = 768) -> bytes:
        params: dict[str, Any] = {"w": w, "width_px": width_px, "height_px": height_px}
        if x is not None:
            params["x"] = x
        if z is not None:
            params["z"] = z
        r = self._client.get("/screenshot", params=params, timeout=30)
        if r.headers.get("content-type", "").startswith("image/"):
            return r.content
        raise BridgeError(r.text[:300])

    # ---- helpers ----
    def status(self) -> dict[str, Any]:
        return self.call("game.status")

    def wait_for(self, state: str = "playing", timeout: float = 300) -> dict[str, Any]:
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                s = self.status()
                if s.get("state") == state:
                    return s
            except BridgeError:
                pass
            time.sleep(2)
        raise BridgeError(f"game did not reach state {state!r} within {timeout}s")

    def wait_alive(self, timeout: float = 600) -> None:
        t0 = time.time()
        while time.time() - t0 < timeout:
            h = self.health()
            if h and h.get("mainThreadAlive"):
                return
            time.sleep(3)
        raise BridgeError("bridge never came up")
