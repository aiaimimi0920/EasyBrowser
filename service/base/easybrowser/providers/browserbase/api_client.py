from __future__ import annotations

import os
from typing import Any

import aiohttp


class BrowserbaseApiClient:
    """HTTP client for the Browserbase REST API.

    Requires BROWSERBASE_API_KEY and optionally BROWSERBASE_PROJECT_ID
    environment variables.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        project_id: str | None = None,
        base_url: str = "https://api.browserbase.com",
    ) -> None:
        self._api_key = api_key or os.environ.get("BROWSERBASE_API_KEY", "")
        self._project_id = project_id or os.environ.get("BROWSERBASE_PROJECT_ID", "")
        self._base_url = base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "x-bb-api-key": self._api_key,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                }
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request(self, method: str, path: str, *, json: Any = None) -> dict[str, Any]:
        session = await self._ensure_session()
        url = f"{self._base_url}{path}"
        async with session.request(method, url, json=json) as resp:
            if not resp.ok:
                text = await resp.text()
                raise RuntimeError(f"Browserbase API error {resp.status}: {text}")
            data = await resp.json()
            return data

    async def create_session(
        self,
        *,
        project_id: str | None = None,
        proxies: list[dict[str, Any]] | None = None,
        browser_settings: dict[str, Any] | None = None,
        keep_alive: bool = False,
        region: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "projectId": project_id or self._project_id,
        }
        if proxies:
            body["proxies"] = proxies
        if browser_settings:
            body["browserSettings"] = browser_settings
        if keep_alive:
            body["keepAlive"] = True
        if region:
            body["region"] = region
        return await self._request("POST", "/v1/sessions", json=body)

    async def get_session(self, session_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v1/sessions/{session_id}")

    async def list_sessions(self) -> list[dict[str, Any]]:
        result = await self._request("GET", "/v1/sessions")
        return result if isinstance(result, list) else [result]

    async def close_session(self, session_id: str, *, project_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "status": "REQUEST_RELEASE",
            "projectId": project_id or self._project_id,
        }
        return await self._request("POST", f"/v1/sessions/{session_id}", json=body)
