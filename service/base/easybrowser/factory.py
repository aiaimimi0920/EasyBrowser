from __future__ import annotations

from typing import Any

from .interfaces.provider import BrowserProvider
from .providers.registry import create_provider, list_providers


def create_browser(provider: str = "chrome", **kwargs: Any) -> BrowserProvider:
    """Factory function to create a browser provider by name.

    Args:
        provider: Provider name — "chrome", "camoufox", "geekez", or "browserbase".
        **kwargs: Provider-specific constructor arguments.

    Returns:
        A BrowserProvider instance ready for launch() or connect().

    Example::

        provider = create_browser("chrome")
        ctx = await provider.launch(LaunchOptions(headless=True))
        page = await ctx.new_page()
        await page.goto("https://example.com")
    """
    return create_provider(provider, **kwargs)


def available_providers() -> list[str]:
    """Return the list of registered provider names."""
    return list_providers()
