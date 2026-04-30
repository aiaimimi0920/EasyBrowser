"""Proxy extension helpers migrated from legacy runtime.

This module is a thin wrapper around the migrated driver_factory logic.
The legacy behavior lives in driver_factory.create_proxy_extension.
"""

from __future__ import annotations

from typing import Any

from . import driver_factory


def create_proxy_extension(*args: Any, **kwargs: Any) -> str | None:
    """Compatibility wrapper for proxy extension creation."""
    return driver_factory.create_proxy_extension(*args, **kwargs)
