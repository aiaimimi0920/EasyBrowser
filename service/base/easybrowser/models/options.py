from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass(frozen=True)
class ProxyConfig:
    server: str
    username: str | None = None
    password: str | None = None
    bypass: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True)
class FingerprintConfig:
    user_agent: str | None = None
    platform: str | None = None
    timezone: str | None = None
    locale: str | None = None
    screen_width: int | None = None
    screen_height: int | None = None
    webgl_vendor: str | None = None
    webgl_renderer: str | None = None
    hardware_concurrency: int | None = None
    device_memory: int | None = None
    browser_type: str | None = None
    browser_version: str | None = None


@dataclasses.dataclass(frozen=True)
class LaunchOptions:
    headless: bool = True
    proxy: ProxyConfig | None = None
    fingerprint: FingerprintConfig | None = None
    browser_binary: str | None = None
    user_data_dir: str | None = None
    extra_args: list[str] = dataclasses.field(default_factory=list)
    timeout_ms: int = 30000
    extra: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class ContextOptions:
    viewport: tuple[int, int] | None = None
    user_agent: str | None = None
    locale: str | None = None
    timezone_id: str | None = None
    geolocation: dict[str, float] | None = None
    permissions: list[str] = dataclasses.field(default_factory=list)
    proxy: ProxyConfig | None = None
    storage_state: dict[str, Any] | None = None
    extra: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class NavigationOptions:
    wait_until: str = "domcontentloaded"
    timeout_ms: int = 30000
    referer: str | None = None


@dataclasses.dataclass(frozen=True)
class ScreenshotOptions:
    path: str | None = None
    full_page: bool = False
    format: str = "png"
    quality: int | None = None
    clip: dict[str, int] | None = None


@dataclasses.dataclass(frozen=True)
class WaitForSelectorOptions:
    state: str = "visible"
    timeout_ms: int = 30000
