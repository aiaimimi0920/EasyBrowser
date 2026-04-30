"""Profile lifecycle helpers migrated from legacy runtime."""

from __future__ import annotations

from typing import Any

from . import driver_factory


def cleanup_stale_profile_state(profile_dir: str) -> None:
    """Remove stale Chrome startup artifacts for a given profile directory."""
    driver_factory._cleanup_stale_browser_startup_state(profile_dir)


def remove_profile_state_path(path: str) -> bool:
    """Remove a profile file or directory path."""
    return driver_factory._remove_browser_state_path(path)


def normalize_browser_backend(value: str | None) -> str:
    """Normalize browser backend value (legacy behavior)."""
    return driver_factory.normalize_browser_backend(value)


def build_stealth_profile(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Proxy to legacy stealth profile construction."""
    return driver_factory.build_stealth_profile(*args, **kwargs)
