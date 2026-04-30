from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models.options import LaunchOptions
from .context import BrowserContext


class BrowserProvider(ABC):
    """Top-level provider — launches/connects to a browser instance."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def launch(self, options: LaunchOptions | None = None) -> BrowserContext: ...

    @abstractmethod
    async def connect(self, endpoint: str, **kwargs: Any) -> BrowserContext: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def is_connected(self) -> bool: ...

    @abstractmethod
    def capabilities(self) -> dict[str, Any]: ...
