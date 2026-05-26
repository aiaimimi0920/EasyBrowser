from __future__ import annotations

import os
from typing import Any

from . import driver_factory
from .stealth_helpers import env_flag, extract_user_agent_bits
from .stealth_source import build_stealth_source


def _build_stealth_profile(driver: Any, headless: int) -> dict[str, Any]:
    return driver_factory.build_stealth_profile(
        driver,
        headless=headless,
        detect_runtime_user_agent_fn=lambda d: driver_factory.detect_runtime_user_agent(
            d,
            resolve_chrome_version_main_fn=driver_factory.resolve_chrome_version_main,
            env_flag_fn=env_flag,
        ),
        extract_user_agent_bits_fn=extract_user_agent_bits,
    )


def apply_runtime_stealth(driver: Any, *, headless: int) -> dict[str, Any]:
    return driver_factory.apply_runtime_stealth(
        driver,
        headless=headless,
        build_stealth_profile_fn=_build_stealth_profile,
        build_stealth_source_fn=build_stealth_source,
    )


def create_anonymous_driver(
    *,
    proxy: str | None = None,
    browser_backend: str = "custom",
    startup_url: str = "",
    startup_user_agent: str = "",
    browser_user_data_dir: str = "",
    browser_profile_directory: str = "",
    browser_debugger_address: str = "",
    remove_args: set[str] | None = None,
) -> tuple[Any, str | None]:
    return driver_factory.new_driver(
        proxy,
        browser_backend=browser_backend,
        create_proxy_extension_fn=driver_factory.create_proxy_extension,
        apply_runtime_stealth_fn=apply_runtime_stealth,
        resolve_chrome_version_main_fn=driver_factory.resolve_chrome_version_main,
        startup_user_agent=startup_user_agent,
        browser_user_data_dir=browser_user_data_dir or str(os.environ.get("BROWSER_USER_DATA_DIR", "") or "").strip(),
        browser_profile_directory=browser_profile_directory or str(os.environ.get("BROWSER_PROFILE_DIRECTORY", "") or "").strip(),
        browser_debugger_address=browser_debugger_address or str(os.environ.get("BROWSER_DEBUGGER_ADDRESS", "") or "").strip(),
        startup_url=startup_url,
        remove_args=remove_args,
    )


if __name__ == "__main__":
    driver, proxy_dir = create_anonymous_driver()
    try:
        print("[chrome-runtime] driver started", flush=True)
        print(f"[chrome-runtime] proxy_dir={proxy_dir or 'none'}", flush=True)
    finally:
        try:
            driver.quit()
        except Exception:
            pass
