from __future__ import annotations

from typing import Any

__all__ = ["BrowserRegistrationResult", "run_registration_once"]


def __getattr__(name: str) -> Any:
    if name in {"BrowserRegistrationResult", "run_registration_once"}:
        from .runner import BrowserRegistrationResult, run_registration_once

        exports = {
            "BrowserRegistrationResult": BrowserRegistrationResult,
            "run_registration_once": run_registration_once,
        }
        return exports[name]
    raise AttributeError(f"module 'browser_runtime' has no attribute {name!r}")
