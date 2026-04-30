from __future__ import annotations

from typing import Any

from ..interfaces.provider import BrowserProvider
from ..models.errors import ProviderNotFoundError

_REGISTRY: dict[str, type[BrowserProvider]] = {}


def register_provider(name: str, cls: type[BrowserProvider]) -> None:
    _REGISTRY[name.lower()] = cls


def get_provider_class(name: str) -> type[BrowserProvider]:
    cls = _REGISTRY.get(name.lower())
    if cls is None:
        available = ", ".join(sorted(_REGISTRY.keys())) or "(none)"
        raise ProviderNotFoundError(
            f"Unknown provider: {name!r}. Available: {available}"
        )
    return cls


def list_providers() -> list[str]:
    return sorted(_REGISTRY.keys())


def create_provider(name: str, **kwargs: Any) -> BrowserProvider:
    cls = get_provider_class(name)
    return cls(**kwargs)


# Auto-register built-in providers
def _auto_register() -> None:
    from .chrome import ChromeProvider
    register_provider("chrome", ChromeProvider)

    from .camoufox import CamoufoxProvider
    register_provider("camoufox", CamoufoxProvider)

    from .geekez import GeekezProvider
    register_provider("geekez", GeekezProvider)

    from .browserbase import BrowserbaseProvider
    register_provider("browserbase", BrowserbaseProvider)


_auto_register()
