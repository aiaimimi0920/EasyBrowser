from __future__ import annotations

from typing import Any

_SOURCE_URL_SUFFIX = "//# sourceURL=__puppeteer_evaluation_script__"
_METHOD_FIELDS = {
    "Runtime.evaluate": "expression",
    "Runtime.callFunctionOn": "functionDeclaration",
}


def patch_driver_sourceurl(driver: Any) -> bool:
    original = getattr(driver, "execute_cdp_cmd", None)
    if original is None or getattr(driver, "_sourceurl_patch_applied", False):
        return False

    def wrapped(method: str, params: dict[str, Any] | None):
        field = _METHOD_FIELDS.get(method)
        if field and isinstance(params, dict):
            value = params.get(field)
            if isinstance(value, str) and _SOURCE_URL_SUFFIX in value:
                params = dict(params)
                params[field] = value.replace(_SOURCE_URL_SUFFIX, "")
        return original(method, params)

    setattr(driver, "execute_cdp_cmd", wrapped)
    setattr(driver, "_sourceurl_patch_applied", True)
    return True
