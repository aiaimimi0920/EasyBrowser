from __future__ import annotations

from typing import Any, Callable

from ...interfaces.page import BrowserPage
from ...models.options import NavigationOptions, ScreenshotOptions, WaitForSelectorOptions


class PlaywrightPage(BrowserPage):
    """BrowserPage adapter wrapping a Playwright async Page object.

    Shared by Camoufox, GeekezBrowser, and Browserbase providers.
    """

    def __init__(self, page: Any) -> None:
        self._page = page

    # --- Navigation ---

    async def goto(self, url: str, *, options: NavigationOptions | None = None) -> None:
        opts = options or NavigationOptions()
        await self._page.goto(
            url,
            wait_until=opts.wait_until,
            timeout=opts.timeout_ms,
            referer=opts.referer,
        )

    async def reload(self, *, options: NavigationOptions | None = None) -> None:
        opts = options or NavigationOptions()
        await self._page.reload(wait_until=opts.wait_until, timeout=opts.timeout_ms)

    async def go_back(self, *, options: NavigationOptions | None = None) -> None:
        opts = options or NavigationOptions()
        await self._page.go_back(wait_until=opts.wait_until, timeout=opts.timeout_ms)

    async def go_forward(self, *, options: NavigationOptions | None = None) -> None:
        opts = options or NavigationOptions()
        await self._page.go_forward(wait_until=opts.wait_until, timeout=opts.timeout_ms)

    # --- Interaction ---

    async def click(self, selector: str, *, timeout_ms: int = 30000) -> None:
        await self._page.click(selector, timeout=timeout_ms)

    async def dblclick(self, selector: str, *, timeout_ms: int = 30000) -> None:
        await self._page.dblclick(selector, timeout=timeout_ms)

    async def hover(self, selector: str, *, timeout_ms: int = 30000) -> None:
        await self._page.hover(selector, timeout=timeout_ms)

    async def tap(self, selector: str, *, timeout_ms: int = 30000) -> None:
        await self._page.tap(selector, timeout=timeout_ms)

    async def focus(self, selector: str, *, timeout_ms: int = 30000) -> None:
        await self._page.focus(selector, timeout=timeout_ms)

    async def drag_and_drop(self, source: str, target: str, *, timeout_ms: int = 30000) -> None:
        await self._page.drag_and_drop(source, target, timeout=timeout_ms)

    async def fill(self, selector: str, value: str, *, timeout_ms: int = 30000) -> None:
        await self._page.fill(selector, value, timeout=timeout_ms)

    async def type(self, selector: str, text: str, *, delay_ms: int = 0, timeout_ms: int = 30000) -> None:
        await self._page.type(selector, text, delay=delay_ms, timeout=timeout_ms)

    async def press(self, selector: str, key: str, *, timeout_ms: int = 30000) -> None:
        await self._page.press(selector, key, timeout=timeout_ms)

    async def select_option(self, selector: str, value: str | list[str], *, timeout_ms: int = 30000) -> list[str]:
        return await self._page.select_option(selector, value, timeout=timeout_ms)

    async def check(self, selector: str, *, timeout_ms: int = 30000) -> None:
        await self._page.check(selector, timeout=timeout_ms)

    async def uncheck(self, selector: str, *, timeout_ms: int = 30000) -> None:
        await self._page.uncheck(selector, timeout=timeout_ms)

    # --- Evaluation ---

    async def evaluate(self, expression: str, *args: Any) -> Any:
        if len(args) == 0:
            return await self._page.evaluate(expression)
        elif len(args) == 1:
            return await self._page.evaluate(expression, args[0])
        else:
            return await self._page.evaluate(expression, list(args))

    # --- Querying ---

    async def query_selector(self, selector: str) -> Any | None:
        return await self._page.query_selector(selector)

    async def query_selector_all(self, selector: str) -> list[Any]:
        return await self._page.query_selector_all(selector)

    # --- Waiting ---

    async def wait_for_selector(self, selector: str, *, options: WaitForSelectorOptions | None = None) -> Any:
        opts = options or WaitForSelectorOptions()
        return await self._page.wait_for_selector(selector, state=opts.state, timeout=opts.timeout_ms)

    async def wait_for_url(self, url_pattern: str, *, timeout_ms: int = 30000) -> None:
        await self._page.wait_for_url(url_pattern, timeout=timeout_ms)

    async def wait_for_load_state(self, state: str = "load", *, timeout_ms: int = 30000) -> None:
        await self._page.wait_for_load_state(state, timeout=timeout_ms)

    async def wait_for_function(self, expression: str, *, arg: Any = None, timeout_ms: int = 30000) -> Any:
        return await self._page.wait_for_function(expression, arg=arg, timeout=timeout_ms)

    # --- Content ---

    async def screenshot(self, *, options: ScreenshotOptions | None = None) -> bytes:
        opts = options or ScreenshotOptions()
        kwargs: dict[str, Any] = {
            "full_page": opts.full_page,
            "type": opts.format,
        }
        if opts.path:
            kwargs["path"] = opts.path
        if opts.quality is not None and opts.format == "jpeg":
            kwargs["quality"] = opts.quality
        return await self._page.screenshot(**kwargs)

    async def pdf(self, *, path: str | None = None, **kwargs: Any) -> bytes:
        pdf_kwargs: dict[str, Any] = dict(kwargs)
        if path:
            pdf_kwargs["path"] = path
        return await self._page.pdf(**pdf_kwargs)

    async def content(self) -> str:
        return await self._page.content()

    async def set_content(self, html: str, *, options: NavigationOptions | None = None) -> None:
        opts = options or NavigationOptions()
        await self._page.set_content(html, wait_until=opts.wait_until, timeout=opts.timeout_ms)

    async def title(self) -> str:
        return await self._page.title()

    @property
    def url(self) -> str:
        return str(self._page.url or "")

    async def inner_text(self, selector: str, *, timeout_ms: int = 30000) -> str:
        return await self._page.inner_text(selector, timeout=timeout_ms)

    async def inner_html(self, selector: str, *, timeout_ms: int = 30000) -> str:
        return await self._page.inner_html(selector, timeout=timeout_ms)

    async def get_attribute(self, selector: str, name: str, *, timeout_ms: int = 30000) -> str | None:
        return await self._page.get_attribute(selector, name, timeout=timeout_ms)

    async def input_value(self, selector: str, *, timeout_ms: int = 30000) -> str:
        return await self._page.input_value(selector, timeout=timeout_ms)

    async def is_visible(self, selector: str) -> bool:
        return await self._page.is_visible(selector)

    # --- Page configuration ---

    async def set_viewport_size(self, width: int, height: int) -> None:
        await self._page.set_viewport_size({"width": width, "height": height})

    async def set_extra_http_headers(self, headers: dict[str, str]) -> None:
        await self._page.set_extra_http_headers(headers)

    # --- Script / Style injection ---

    async def add_script_tag(self, *, url: str | None = None, content: str | None = None) -> None:
        kwargs: dict[str, str] = {}
        if url:
            kwargs["url"] = url
        elif content:
            kwargs["content"] = content
        await self._page.add_script_tag(**kwargs)

    async def add_style_tag(self, *, url: str | None = None, content: str | None = None) -> None:
        kwargs: dict[str, str] = {}
        if url:
            kwargs["url"] = url
        elif content:
            kwargs["content"] = content
        await self._page.add_style_tag(**kwargs)

    # --- Frames ---

    async def frames(self) -> list[Any]:
        return list(self._page.frames)

    async def frame(self, *, name: str | None = None, url: str | None = None) -> Any | None:
        if name:
            return self._page.frame(name=name)
        if url:
            return self._page.frame(url=url)
        return None

    # --- Network interception ---

    async def route(self, url: str, handler: Callable[..., Any]) -> None:
        await self._page.route(url, handler)

    async def unroute(self, url: str) -> None:
        await self._page.unroute(url)

    # --- Lifecycle ---

    async def close(self) -> None:
        await self._page.close()

    async def bring_to_front(self) -> None:
        await self._page.bring_to_front()

    def unwrap(self) -> Any:
        return self._page
