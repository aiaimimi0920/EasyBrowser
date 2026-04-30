from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Callable

from ..models.options import NavigationOptions, ScreenshotOptions, WaitForSelectorOptions


class BrowserPage(ABC):
    """Playwright-style page interface. Every provider adapter implements this."""

    # --- Navigation ---

    @abstractmethod
    async def goto(self, url: str, *, options: NavigationOptions | None = None) -> None: ...

    @abstractmethod
    async def reload(self, *, options: NavigationOptions | None = None) -> None: ...

    @abstractmethod
    async def go_back(self, *, options: NavigationOptions | None = None) -> None: ...

    @abstractmethod
    async def go_forward(self, *, options: NavigationOptions | None = None) -> None: ...

    # --- Interaction ---

    @abstractmethod
    async def click(self, selector: str, *, timeout_ms: int = 30000) -> None: ...

    @abstractmethod
    async def dblclick(self, selector: str, *, timeout_ms: int = 30000) -> None: ...

    @abstractmethod
    async def hover(self, selector: str, *, timeout_ms: int = 30000) -> None: ...

    @abstractmethod
    async def tap(self, selector: str, *, timeout_ms: int = 30000) -> None: ...

    @abstractmethod
    async def focus(self, selector: str, *, timeout_ms: int = 30000) -> None: ...

    @abstractmethod
    async def drag_and_drop(self, source: str, target: str, *, timeout_ms: int = 30000) -> None: ...

    @abstractmethod
    async def fill(self, selector: str, value: str, *, timeout_ms: int = 30000) -> None: ...

    @abstractmethod
    async def type(self, selector: str, text: str, *, delay_ms: int = 0, timeout_ms: int = 30000) -> None: ...

    @abstractmethod
    async def press(self, selector: str, key: str, *, timeout_ms: int = 30000) -> None: ...

    @abstractmethod
    async def select_option(self, selector: str, value: str | list[str], *, timeout_ms: int = 30000) -> list[str]: ...

    @abstractmethod
    async def check(self, selector: str, *, timeout_ms: int = 30000) -> None: ...

    @abstractmethod
    async def uncheck(self, selector: str, *, timeout_ms: int = 30000) -> None: ...

    # --- Evaluation ---

    @abstractmethod
    async def evaluate(self, expression: str, *args: Any) -> Any: ...

    # --- Querying ---

    @abstractmethod
    async def query_selector(self, selector: str) -> Any | None: ...

    @abstractmethod
    async def query_selector_all(self, selector: str) -> list[Any]: ...

    # --- Waiting ---

    @abstractmethod
    async def wait_for_selector(self, selector: str, *, options: WaitForSelectorOptions | None = None) -> Any: ...

    @abstractmethod
    async def wait_for_url(self, url_pattern: str, *, timeout_ms: int = 30000) -> None: ...

    @abstractmethod
    async def wait_for_load_state(self, state: str = "load", *, timeout_ms: int = 30000) -> None: ...

    async def wait_for_timeout(self, timeout_ms: int) -> None:
        await asyncio.sleep(timeout_ms / 1000.0)

    @abstractmethod
    async def wait_for_function(self, expression: str, *, arg: Any = None, timeout_ms: int = 30000) -> Any: ...

    # --- Content ---

    @abstractmethod
    async def screenshot(self, *, options: ScreenshotOptions | None = None) -> bytes: ...

    @abstractmethod
    async def pdf(self, *, path: str | None = None, **kwargs: Any) -> bytes: ...

    @abstractmethod
    async def content(self) -> str: ...

    @abstractmethod
    async def set_content(self, html: str, *, options: NavigationOptions | None = None) -> None: ...

    @abstractmethod
    async def title(self) -> str: ...

    @property
    @abstractmethod
    def url(self) -> str: ...

    @abstractmethod
    async def inner_text(self, selector: str, *, timeout_ms: int = 30000) -> str: ...

    @abstractmethod
    async def inner_html(self, selector: str, *, timeout_ms: int = 30000) -> str: ...

    @abstractmethod
    async def get_attribute(self, selector: str, name: str, *, timeout_ms: int = 30000) -> str | None: ...

    @abstractmethod
    async def input_value(self, selector: str, *, timeout_ms: int = 30000) -> str: ...

    @abstractmethod
    async def is_visible(self, selector: str) -> bool: ...

    # --- Page configuration ---

    @abstractmethod
    async def set_viewport_size(self, width: int, height: int) -> None: ...

    @abstractmethod
    async def set_extra_http_headers(self, headers: dict[str, str]) -> None: ...

    # --- Script / Style injection ---

    @abstractmethod
    async def add_script_tag(self, *, url: str | None = None, content: str | None = None) -> None: ...

    @abstractmethod
    async def add_style_tag(self, *, url: str | None = None, content: str | None = None) -> None: ...

    # --- Frames ---

    @abstractmethod
    async def frames(self) -> list[Any]: ...

    @abstractmethod
    async def frame(self, *, name: str | None = None, url: str | None = None) -> Any | None: ...

    # --- Network interception ---

    @abstractmethod
    async def route(self, url: str, handler: Callable[..., Any]) -> None: ...

    @abstractmethod
    async def unroute(self, url: str) -> None: ...

    # --- Lifecycle ---

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def bring_to_front(self) -> None: ...

    @abstractmethod
    def unwrap(self) -> Any:
        """Return the native underlying driver/page object."""
        ...
