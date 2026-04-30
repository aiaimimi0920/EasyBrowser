from __future__ import annotations

from typing import Any

import aiohttp


class GeekezApiClient:
    """HTTP client for the GeekezBrowser REST API.

    GeekezBrowser exposes a local HTTP server (default port 52000) with endpoints
    for profile management and browser lifecycle control.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:52000") -> None:
        self._base_url = base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request(self, method: str, path: str, *, json: Any = None) -> dict[str, Any]:
        session = await self._ensure_session()
        url = f"{self._base_url}{path}"
        async with session.request(method, url, json=json) as resp:
            data = await resp.json()
            return data

    async def get_status(self) -> dict[str, Any]:
        return await self._request("GET", "/api/status")

    async def list_profiles(self, *, tag: str | None = None) -> list[dict[str, Any]]:
        path = "/api/profiles"
        if tag:
            path = f"{path}?tag={tag}"
        result = await self._request("GET", path)
        return result.get("profiles", [])

    async def get_profile(self, id_or_name: str) -> dict[str, Any]:
        result = await self._request("GET", f"/api/profiles/{id_or_name}")
        return result.get("profile", result)

    async def create_profile(self, data: dict[str, Any]) -> dict[str, Any]:
        result = await self._request("POST", "/api/profiles", json=data)
        return result

    async def update_profile(self, id_or_name: str, data: dict[str, Any]) -> dict[str, Any]:
        result = await self._request("PUT", f"/api/profiles/{id_or_name}", json=data)
        return result

    async def delete_profile(self, id_or_name: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/api/profiles/{id_or_name}")

    async def launch_profile(self, id_or_name: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/open/{id_or_name}")

    async def stop_profile(self, id_or_name: str) -> dict[str, Any]:
        return await self._request("POST", f"/api/profiles/{id_or_name}/stop")
