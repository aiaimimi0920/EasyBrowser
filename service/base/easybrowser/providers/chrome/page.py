from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from ...interfaces.page import BrowserPage
from ...models.errors import ElementNotFoundError, NavigationError, TimeoutError
from ...models.options import NavigationOptions, ScreenshotOptions, WaitForSelectorOptions


# Selenium key name mapping
_KEY_MAP: dict[str, str] = {
    "Enter": Keys.ENTER,
    "Tab": Keys.TAB,
    "Escape": Keys.ESCAPE,
    "Backspace": Keys.BACKSPACE,
    "Delete": Keys.DELETE,
    "ArrowUp": Keys.ARROW_UP,
    "ArrowDown": Keys.ARROW_DOWN,
    "ArrowLeft": Keys.ARROW_LEFT,
    "ArrowRight": Keys.ARROW_RIGHT,
    "Home": Keys.HOME,
    "End": Keys.END,
    "PageUp": Keys.PAGE_UP,
    "PageDown": Keys.PAGE_DOWN,
    "Space": Keys.SPACE,
}


def _to_thread(fn: Any) -> Any:
    return asyncio.to_thread(fn)


class ChromePage(BrowserPage):
    """BrowserPage adapter for Selenium WebDriver."""

    def __init__(self, driver: Any, *, window_handle: str | None = None) -> None:
        self._driver = driver
        self._window_handle = window_handle
        self._closed = False

    def _ensure_active(self) -> None:
        if self._window_handle and self._driver.current_window_handle != self._window_handle:
            self._driver.switch_to.window(self._window_handle)

    def _find(self, selector: str, timeout_s: float = 10.0) -> Any:
        self._ensure_active()
        if timeout_s > 0:
            WebDriverWait(self._driver, timeout_s).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
        return self._driver.find_element(By.CSS_SELECTOR, selector)

    # --- Navigation ---

    async def goto(self, url: str, *, options: NavigationOptions | None = None) -> None:
        def _go() -> None:
            self._ensure_active()
            self._driver.get(url)
        await _to_thread(_go)

    async def reload(self, *, options: NavigationOptions | None = None) -> None:
        await _to_thread(lambda: (self._ensure_active(), self._driver.refresh()))

    async def go_back(self, *, options: NavigationOptions | None = None) -> None:
        await _to_thread(lambda: (self._ensure_active(), self._driver.back()))

    async def go_forward(self, *, options: NavigationOptions | None = None) -> None:
        await _to_thread(lambda: (self._ensure_active(), self._driver.forward()))

    # --- Interaction ---

    async def click(self, selector: str, *, timeout_ms: int = 30000) -> None:
        def _click() -> None:
            el = self._find(selector, timeout_ms / 1000.0)
            el.click()
        await _to_thread(_click)

    async def dblclick(self, selector: str, *, timeout_ms: int = 30000) -> None:
        def _dblclick() -> None:
            el = self._find(selector, timeout_ms / 1000.0)
            ActionChains(self._driver).double_click(el).perform()
        await _to_thread(_dblclick)

    async def hover(self, selector: str, *, timeout_ms: int = 30000) -> None:
        def _hover() -> None:
            el = self._find(selector, timeout_ms / 1000.0)
            ActionChains(self._driver).move_to_element(el).perform()
        await _to_thread(_hover)

    async def tap(self, selector: str, *, timeout_ms: int = 30000) -> None:
        # Selenium has no native tap; fall back to click
        await self.click(selector, timeout_ms=timeout_ms)

    async def focus(self, selector: str, *, timeout_ms: int = 30000) -> None:
        def _focus() -> None:
            el = self._find(selector, timeout_ms / 1000.0)
            self._driver.execute_script("arguments[0].focus();", el)
        await _to_thread(_focus)

    async def drag_and_drop(self, source: str, target: str, *, timeout_ms: int = 30000) -> None:
        def _dnd() -> None:
            src = self._find(source, timeout_ms / 1000.0)
            tgt = self._find(target, timeout_ms / 1000.0)
            ActionChains(self._driver).drag_and_drop(src, tgt).perform()
        await _to_thread(_dnd)

    async def fill(self, selector: str, value: str, *, timeout_ms: int = 30000) -> None:
        def _fill() -> None:
            el = self._find(selector, timeout_ms / 1000.0)
            el.clear()
            el.send_keys(value)
        await _to_thread(_fill)

    async def type(self, selector: str, text: str, *, delay_ms: int = 0, timeout_ms: int = 30000) -> None:
        def _type() -> None:
            el = self._find(selector, timeout_ms / 1000.0)
            if delay_ms <= 0:
                el.send_keys(text)
            else:
                for ch in text:
                    el.send_keys(ch)
                    time.sleep(delay_ms / 1000.0)
        await _to_thread(_type)

    async def press(self, selector: str, key: str, *, timeout_ms: int = 30000) -> None:
        def _press() -> None:
            el = self._find(selector, timeout_ms / 1000.0)
            selenium_key = _KEY_MAP.get(key, key)
            el.send_keys(selenium_key)
        await _to_thread(_press)

    async def select_option(self, selector: str, value: str | list[str], *, timeout_ms: int = 30000) -> list[str]:
        def _select() -> list[str]:
            el = self._find(selector, timeout_ms / 1000.0)
            sel = Select(el)
            values = [value] if isinstance(value, str) else value
            for v in values:
                sel.select_by_value(v)
            return [o.get_attribute("value") or "" for o in sel.all_selected_options]
        return await _to_thread(_select)

    async def check(self, selector: str, *, timeout_ms: int = 30000) -> None:
        def _check() -> None:
            el = self._find(selector, timeout_ms / 1000.0)
            if not el.is_selected():
                el.click()
        await _to_thread(_check)

    async def uncheck(self, selector: str, *, timeout_ms: int = 30000) -> None:
        def _uncheck() -> None:
            el = self._find(selector, timeout_ms / 1000.0)
            if el.is_selected():
                el.click()
        await _to_thread(_uncheck)

    # --- Evaluation ---

    async def evaluate(self, expression: str, *args: Any) -> Any:
        def _eval() -> Any:
            self._ensure_active()
            return self._driver.execute_script(expression, *args)
        return await _to_thread(_eval)

    # --- Querying ---

    async def query_selector(self, selector: str) -> Any | None:
        def _qs() -> Any | None:
            self._ensure_active()
            elements = self._driver.find_elements(By.CSS_SELECTOR, selector)
            return elements[0] if elements else None
        return await _to_thread(_qs)

    async def query_selector_all(self, selector: str) -> list[Any]:
        def _qsa() -> list[Any]:
            self._ensure_active()
            return self._driver.find_elements(By.CSS_SELECTOR, selector)
        return await _to_thread(_qsa)

    # --- Waiting ---

    async def wait_for_selector(self, selector: str, *, options: WaitForSelectorOptions | None = None) -> Any:
        opts = options or WaitForSelectorOptions()

        def _wait() -> Any:
            self._ensure_active()
            timeout_s = opts.timeout_ms / 1000.0
            if opts.state in ("visible", "attached"):
                return WebDriverWait(self._driver, timeout_s).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
            elif opts.state == "hidden":
                WebDriverWait(self._driver, timeout_s).until(
                    EC.invisibility_of_element_located((By.CSS_SELECTOR, selector))
                )
                return None
            elif opts.state == "detached":
                WebDriverWait(self._driver, timeout_s).until_not(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                return None
            return WebDriverWait(self._driver, timeout_s).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
        return await _to_thread(_wait)

    async def wait_for_url(self, url_pattern: str, *, timeout_ms: int = 30000) -> None:
        def _wait() -> None:
            self._ensure_active()
            WebDriverWait(self._driver, timeout_ms / 1000.0).until(EC.url_contains(url_pattern))
        await _to_thread(_wait)

    async def wait_for_load_state(self, state: str = "load", *, timeout_ms: int = 30000) -> None:
        def _wait() -> None:
            self._ensure_active()
            if state in ("load", "domcontentloaded"):
                WebDriverWait(self._driver, timeout_ms / 1000.0).until(
                    lambda d: d.execute_script("return document.readyState") in ("complete", "interactive")
                )
        await _to_thread(_wait)

    async def wait_for_function(self, expression: str, *, arg: Any = None, timeout_ms: int = 30000) -> Any:
        def _wait() -> Any:
            self._ensure_active()
            WebDriverWait(self._driver, timeout_ms / 1000.0).until(
                lambda d: d.execute_script(f"return Boolean({expression})")
            )
            return self._driver.execute_script(f"return ({expression})")
        return await _to_thread(_wait)

    # --- Content ---

    async def screenshot(self, *, options: ScreenshotOptions | None = None) -> bytes:
        def _ss() -> bytes:
            self._ensure_active()
            data = self._driver.get_screenshot_as_png()
            opts = options
            if opts and opts.path:
                with open(opts.path, "wb") as f:
                    f.write(data)
            return data
        return await _to_thread(_ss)

    async def content(self) -> str:
        def _content() -> str:
            self._ensure_active()
            return str(self._driver.page_source or "")
        return await _to_thread(_content)

    async def title(self) -> str:
        def _title() -> str:
            self._ensure_active()
            return str(self._driver.title or "")
        return await _to_thread(_title)

    @property
    def url(self) -> str:
        try:
            self._ensure_active()
            return str(self._driver.current_url or "")
        except Exception:
            return ""

    async def inner_text(self, selector: str, *, timeout_ms: int = 30000) -> str:
        def _it() -> str:
            el = self._find(selector, timeout_ms / 1000.0)
            return str(el.text or "")
        return await _to_thread(_it)

    async def inner_html(self, selector: str, *, timeout_ms: int = 30000) -> str:
        def _ih() -> str:
            el = self._find(selector, timeout_ms / 1000.0)
            return str(el.get_attribute("innerHTML") or "")
        return await _to_thread(_ih)

    async def get_attribute(self, selector: str, name: str, *, timeout_ms: int = 30000) -> str | None:
        def _ga() -> str | None:
            el = self._find(selector, timeout_ms / 1000.0)
            return el.get_attribute(name)
        return await _to_thread(_ga)

    async def input_value(self, selector: str, *, timeout_ms: int = 30000) -> str:
        def _iv() -> str:
            el = self._find(selector, timeout_ms / 1000.0)
            return str(el.get_attribute("value") or "")
        return await _to_thread(_iv)

    async def is_visible(self, selector: str) -> bool:
        def _iv() -> bool:
            self._ensure_active()
            elements = self._driver.find_elements(By.CSS_SELECTOR, selector)
            return bool(elements and elements[0].is_displayed())
        return await _to_thread(_iv)

    async def pdf(self, *, path: str | None = None, **kwargs: Any) -> bytes:
        def _pdf() -> bytes:
            self._ensure_active()
            params: dict[str, Any] = {}
            if "landscape" in kwargs:
                params["landscape"] = kwargs["landscape"]
            result = self._driver.execute_cdp_cmd("Page.printToPDF", params)
            import base64
            data = base64.b64decode(result["data"])
            if path:
                with open(path, "wb") as f:
                    f.write(data)
            return data
        return await _to_thread(_pdf)

    async def set_content(self, html: str, *, options: NavigationOptions | None = None) -> None:
        def _set() -> None:
            self._ensure_active()
            self._driver.execute_script("document.open(); document.write(arguments[0]); document.close();", html)
        await _to_thread(_set)

    async def set_viewport_size(self, width: int, height: int) -> None:
        def _set() -> None:
            self._ensure_active()
            self._driver.set_window_size(width, height)
        await _to_thread(_set)

    async def set_extra_http_headers(self, headers: dict[str, str]) -> None:
        def _set() -> None:
            self._ensure_active()
            try:
                self._driver.execute_cdp_cmd("Network.enable", {})
                self._driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {"headers": headers})
            except Exception:
                pass
        await _to_thread(_set)

    async def add_script_tag(self, *, url: str | None = None, content: str | None = None) -> None:
        def _add() -> None:
            self._ensure_active()
            if url:
                self._driver.execute_script(
                    "var s=document.createElement('script');s.src=arguments[0];document.head.appendChild(s);", url
                )
            elif content:
                self._driver.execute_script(
                    "var s=document.createElement('script');s.textContent=arguments[0];document.head.appendChild(s);", content
                )
        await _to_thread(_add)

    async def add_style_tag(self, *, url: str | None = None, content: str | None = None) -> None:
        def _add() -> None:
            self._ensure_active()
            if url:
                self._driver.execute_script(
                    "var l=document.createElement('link');l.rel='stylesheet';l.href=arguments[0];document.head.appendChild(l);", url
                )
            elif content:
                self._driver.execute_script(
                    "var s=document.createElement('style');s.textContent=arguments[0];document.head.appendChild(s);", content
                )
        await _to_thread(_add)

    async def frames(self) -> list[Any]:
        def _frames() -> list[Any]:
            self._ensure_active()
            iframes = self._driver.find_elements(By.TAG_NAME, "iframe")
            return list(iframes)
        return await _to_thread(_frames)

    async def frame(self, *, name: str | None = None, url: str | None = None) -> Any | None:
        def _frame() -> Any | None:
            self._ensure_active()
            if name:
                try:
                    self._driver.switch_to.frame(name)
                    return self._driver
                except Exception:
                    return None
            if url:
                iframes = self._driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    src = iframe.get_attribute("src") or ""
                    if url in src:
                        self._driver.switch_to.frame(iframe)
                        return self._driver
            return None
        return await _to_thread(_frame)

    async def route(self, url: str, handler: Callable[..., Any]) -> None:
        # Selenium does not support network interception natively.
        # Use CDP Network.setBlockedURLs for basic blocking, or use unwrap() for full CDP access.
        pass

    async def unroute(self, url: str) -> None:
        pass

    # --- Lifecycle ---

    async def close(self) -> None:
        def _close() -> None:
            if self._closed:
                return
            self._ensure_active()
            self._driver.close()
            self._closed = True
        await _to_thread(_close)

    async def bring_to_front(self) -> None:
        def _btf() -> None:
            if self._window_handle:
                self._driver.switch_to.window(self._window_handle)
        await _to_thread(_btf)

    def unwrap(self) -> Any:
        return self._driver
