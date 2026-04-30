from __future__ import annotations

from ...interfaces.page import BrowserPage
from ...models.options import NavigationOptions
from ...models.results import TaskConfig, TaskResult
from ..handler import TaskHandler


class NavigateHandler(TaskHandler):
    """Simple navigation task handler.

    Navigates to a URL and returns the page title and final URL.

    Params:
        url (str): Target URL to navigate to.
        wait_until (str): Navigation wait condition (default: "domcontentloaded").
        screenshot (bool): Whether to take a screenshot after navigation (default: False).
    """

    async def run(self, page: BrowserPage, config: TaskConfig) -> TaskResult:
        url = config.params.get("url", "")
        if not url:
            return TaskResult(
                success=False,
                task_type=config.task_type,
                provider=config.provider or "",
                error="Missing 'url' in params",
            )

        wait_until = config.params.get("wait_until", "domcontentloaded")
        await page.goto(url, options=NavigationOptions(wait_until=wait_until))

        title = await page.title()
        final_url = page.url

        data: dict[str, object] = {
            "title": title,
            "url": final_url,
        }

        if config.params.get("screenshot"):
            screenshot_bytes = await page.screenshot()
            data["screenshot_size"] = len(screenshot_bytes)

        return TaskResult(
            success=True,
            task_type=config.task_type,
            provider=config.provider or "",
            data=data,
        )
