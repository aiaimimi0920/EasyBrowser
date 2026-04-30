from __future__ import annotations

from . import driver_factory


def cleanup_stale_profile_state(user_data_dir: str) -> None:
    driver_factory._cleanup_stale_browser_startup_state(user_data_dir)
