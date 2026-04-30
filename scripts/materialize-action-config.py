#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import yaml


def deep_merge(base: Any, overlay: Any) -> Any:
    if overlay is None:
        return base
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = dict(base)
        for key, value in overlay.items():
            if key in merged:
                merged[key] = deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged
    return overlay


def load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Base config not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}


def build_overlay() -> dict[str, Any]:
    overlay: dict[str, Any] = {}

    service_listen = os.environ.get("EASYBROWSER_SERVICE_LISTEN", "").strip()
    chrome_headless = os.environ.get("EASYBROWSER_CHROME_HEADLESS", "").strip()
    chrome_uc = os.environ.get("EASYBROWSER_CHROME_USE_UNDETECTED_CHROMEDRIVER", "").strip()
    chrome_binary_path = os.environ.get("EASYBROWSER_CHROME_BINARY_PATH", "").strip()
    chromedriver_path = os.environ.get("EASYBROWSER_CHROMEDRIVER_PATH", "").strip()
    chrome_python_path = os.environ.get("EASYBROWSER_CHROME_PYTHON", "").strip()
    camoufox_python_path = os.environ.get("EASYBROWSER_CAMOUFOX_PYTHON", "").strip()
    camoufox_headless = os.environ.get("EASYBROWSER_CAMOUFOX_HEADLESS", "").strip()
    camoufox_os = os.environ.get("EASYBROWSER_CAMOUFOX_OS", "").strip()
    camoufox_ready_timeout = os.environ.get("EASYBROWSER_CAMOUFOX_READY_TIMEOUT_MS", "").strip()
    geekez_python_path = os.environ.get("EASYBROWSER_GEEKEZ_PYTHON", "").strip()
    geekez_ready_timeout = os.environ.get("EASYBROWSER_GEEKEZ_READY_TIMEOUT_MS", "").strip()
    browserbase_api_key = os.environ.get("EASYBROWSER_BROWSERBASE_API_KEY", "").strip()
    browserbase_project_id = os.environ.get("EASYBROWSER_BROWSERBASE_PROJECT_ID", "").strip()
    ghcr_image_name = os.environ.get("EASYBROWSER_GHCR_IMAGE_NAME", "").strip()
    ghcr_namespace = os.environ.get("EASYBROWSER_GHCR_NAMESPACE", "").strip()
    ghcr_registry = os.environ.get("EASYBROWSER_GHCR_REGISTRY", "").strip()
    import_sync_enabled = os.environ.get("EASYBROWSER_IMPORT_CODE_SYNC_ENABLED", "").strip()
    import_sync_interval = os.environ.get("EASYBROWSER_IMPORT_CODE_SYNC_INTERVAL_SECONDS", "").strip()

    if service_listen:
        overlay.setdefault("serviceBase", {}).setdefault("runtime", {})["listen"] = service_listen

    if chrome_headless:
        normalized = chrome_headless.lower()
        if normalized in {"1", "true", "yes", "on"}:
            value = True
        elif normalized in {"0", "false", "no", "off"}:
            value = False
        else:
            raise SystemExit("EASYBROWSER_CHROME_HEADLESS must be boolean-like")
        overlay.setdefault("chromeRuntime", {})["headless"] = value

    if chrome_uc:
        normalized = chrome_uc.lower()
        if normalized in {"1", "true", "yes", "on"}:
            value = True
        elif normalized in {"0", "false", "no", "off"}:
            value = False
        else:
            raise SystemExit("EASYBROWSER_CHROME_USE_UNDETECTED_CHROMEDRIVER must be boolean-like")
        overlay.setdefault("chromeRuntime", {})["useUndetectedChromedriver"] = value

    if chrome_binary_path:
        overlay.setdefault("chromeRuntime", {})["binaryPath"] = chrome_binary_path
    if chromedriver_path:
        overlay.setdefault("chromeRuntime", {})["chromedriverPath"] = chromedriver_path
    if chrome_python_path:
        overlay.setdefault("chromeRuntime", {})["pythonPath"] = chrome_python_path

    if camoufox_python_path:
        overlay.setdefault("camoufoxRuntime", {})["pythonPath"] = camoufox_python_path
    if camoufox_os:
        overlay.setdefault("camoufoxRuntime", {})["os"] = camoufox_os
    if camoufox_ready_timeout:
        try:
            overlay.setdefault("camoufoxRuntime", {})["readyTimeoutMs"] = int(camoufox_ready_timeout)
        except ValueError as exc:
            raise SystemExit("EASYBROWSER_CAMOUFOX_READY_TIMEOUT_MS must be an integer") from exc
    if camoufox_headless:
        normalized = camoufox_headless.lower()
        if normalized in {"1", "true", "yes", "on"}:
            value = True
        elif normalized in {"0", "false", "no", "off"}:
            value = False
        else:
            raise SystemExit("EASYBROWSER_CAMOUFOX_HEADLESS must be boolean-like")
        overlay.setdefault("camoufoxRuntime", {})["headless"] = value

    if geekez_python_path:
        overlay.setdefault("geekezRuntime", {})["pythonPath"] = geekez_python_path
    if geekez_ready_timeout:
        try:
            overlay.setdefault("geekezRuntime", {})["readyTimeoutMs"] = int(geekez_ready_timeout)
        except ValueError as exc:
            raise SystemExit("EASYBROWSER_GEEKEZ_READY_TIMEOUT_MS must be an integer") from exc

    if browserbase_api_key:
        overlay.setdefault("browserbase", {})["apiKey"] = browserbase_api_key
    if browserbase_project_id:
        overlay.setdefault("browserbase", {})["projectId"] = browserbase_project_id

    if ghcr_image_name:
        overlay.setdefault("publishing", {}).setdefault("ghcr", {})["imageName"] = ghcr_image_name
    if ghcr_namespace:
        overlay.setdefault("publishing", {}).setdefault("ghcr", {})["namespace"] = ghcr_namespace
    if ghcr_registry:
        overlay.setdefault("publishing", {}).setdefault("ghcr", {})["registry"] = ghcr_registry

    if import_sync_enabled:
        normalized = import_sync_enabled.lower()
        if normalized in {"1", "true", "yes", "on"}:
            value = True
        elif normalized in {"0", "false", "no", "off"}:
            value = False
        else:
            raise SystemExit("EASYBROWSER_IMPORT_CODE_SYNC_ENABLED must be boolean-like")
        overlay.setdefault("publishing", {}).setdefault("importCode", {})["syncEnabled"] = value

    if import_sync_interval:
        try:
            overlay.setdefault("publishing", {}).setdefault("importCode", {})["syncIntervalSeconds"] = int(import_sync_interval)
        except ValueError as exc:
            raise SystemExit("EASYBROWSER_IMPORT_CODE_SYNC_INTERVAL_SECONDS must be an integer") from exc

    return overlay


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    base = load_yaml_file(Path(args.base_config))
    overlay = build_overlay()
    merged = deep_merge(base, overlay)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(merged, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
