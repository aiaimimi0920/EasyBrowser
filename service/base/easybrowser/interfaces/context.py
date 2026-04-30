from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from .page import BrowserPage


class BrowserContext(ABC):
    """Represents an isolated browser context (incognito-like session)."""

    @abstractmethod
    async def new_page(self) -> BrowserPage: ...

    @abstractmethod
    async def pages(self) -> list[BrowserPage]: ...

    # --- Cookies & Storage ---

    @abstractmethod
    async def cookies(self, urls: list[str] | None = None) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def add_cookies(self, cookies: list[dict[str, Any]]) -> None: ...

    @abstractmethod
    async def clear_cookies(self) -> None: ...

    @abstractmethod
    async def storage_state(self) -> dict[str, Any]: ...

    # --- Initialization ---

    @abstractmethod
    async def add_init_script(self, script: str) -> None: ...

    # --- Timeout ---

    @abstractmethod
    async def set_default_timeout(self, timeout_ms: int) -> None: ...

    @abstractmethod
    async def set_default_navigation_timeout(self, timeout_ms: int) -> None: ...

    # --- Permissions ---

    @abstractmethod
    async def grant_permissions(self, permissions: list[str], *, origin: str | None = None) -> None: ...

    @abstractmethod
    async def clear_permissions(self) -> None: ...

    # --- Geolocation & Network ---

    @abstractmethod
    async def set_geolocation(self, geolocation: dict[str, float] | None) -> None: ...

    @abstractmethod
    async def set_offline(self, offline: bool) -> None: ...

    # --- Network interception ---

    @abstractmethod
    async def route(self, url: str, handler: Callable[..., Any]) -> None: ...

    @abstractmethod
    async def unroute(self, url: str) -> None: ...

    # --- Lifecycle ---

    @abstractmethod
    async def close(self) -> None: ...
