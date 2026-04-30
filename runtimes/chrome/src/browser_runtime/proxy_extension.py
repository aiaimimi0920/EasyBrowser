from __future__ import annotations

from . import driver_factory


def create_proxy_extension(proxy: str, base_dir: str | None = None) -> str | None:
    return driver_factory.create_proxy_extension(proxy, base_dir)
