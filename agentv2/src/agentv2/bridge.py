"""Async client for the RimBridge mod: POST /rpc, GET /health /methods /events /screenshot."""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx


class BridgeError(Exception):
    pass


class Bridge:
    def __init__(self, url: str, timeout_s: float = 60.0, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.url = url.rstrip("/")
        self.timeout_s = timeout_s
        self._client = httpx.AsyncClient(base_url=self.url, timeout=timeout_s, transport=transport)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def call(self, method: str, params: dict[str, Any] | None = None, timeout_ms: int | None = None) -> Any:
        envelope = await self.call_raw(method, params, timeout_ms)
        if not envelope.get("ok"):
            raise BridgeError(str(envelope.get("error") or "unknown bridge error"))
        return envelope.get("result")

    async def call_raw(self, method: str, params: dict[str, Any] | None = None, timeout_ms: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"method": method, "params": params or {}}
        if timeout_ms:
            payload["timeout_ms"] = timeout_ms
        try:
            response = await self._client.post("/rpc", json=payload, timeout=(timeout_ms or self.timeout_s * 1000) / 1000 + 5)
        except httpx.HTTPError as e:
            raise BridgeError(f"bridge unreachable: {e}") from e
        try:
            return response.json()
        except ValueError as e:
            raise BridgeError(f"bad bridge response: {response.text[:200]}") from e

    async def health(self) -> dict[str, Any] | None:
        try:
            return (await self._client.get("/health", timeout=3)).json()
        except (httpx.HTTPError, ValueError):
            return None

    async def methods(self) -> list[dict[str, str]]:
        return await self._get_result("/methods", timeout=10)

    async def events(self, since: int, limit: int = 500) -> dict[str, Any]:
        return await self._get_result("/events", params={"since": since, "limit": limit}, timeout=10)

    async def screenshot(self, x: int | None = None, z: int | None = None, w: float = 60, width_px: int = 1024, height_px: int = 768) -> bytes:
        params: dict[str, Any] = {"w": w, "width_px": width_px, "height_px": height_px}
        if x is not None and z is not None:
            params |= {"x": x, "z": z}
        try:
            response = await self._client.get("/screenshot", params=params, timeout=35)
        except httpx.HTTPError as e:
            raise BridgeError(f"bridge unreachable: {e}") from e
        if not response.headers.get("content-type", "").startswith("image/"):
            raise BridgeError(response.text[:300])
        return response.content

    async def status(self) -> dict[str, Any]:
        return await self.call("game.status")

    async def wait_for(self, state: str, timeout: float = 600) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                status = await self.status()
                if status.get("state") == state:
                    return status
            except BridgeError:
                pass
            await asyncio.sleep(2)
        raise BridgeError(f"game did not reach state {state!r} within {timeout:.0f}s")

    async def wait_alive(self, timeout: float = 600) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            health = await self.health()
            if health and health.get("mainThreadAlive"):
                return
            await asyncio.sleep(3)
        raise BridgeError("bridge never came up")

    async def _get_result(self, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._client.get(path, **kwargs)
            return response.json()["result"]
        except (httpx.HTTPError, ValueError, KeyError) as e:
            raise BridgeError(f"{path}: {e}") from e
