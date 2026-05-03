#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


def load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Config not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}


def normalize_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_runtime_env(config: dict[str, Any]) -> dict[str, str]:
    service_base = config.get("serviceBase") or {}
    service_runtime = service_base.get("runtime") or {}
    runtime_pool = service_runtime.get("runtimePool") or {}
    runtime_pool_providers = runtime_pool.get("providers") or {}
    chrome = config.get("chromeRuntime") or {}
    camoufox = config.get("camoufoxRuntime") or {}
    geekez = config.get("geekezRuntime") or {}
    browserbase = config.get("browserbase") or {}

    env: dict[str, str] = {
        "EASYBROWSER_LISTEN": stringify(service_runtime.get("listen") or "127.0.0.1:18080"),
        "EASYBROWSER_RUNTIME_MODE": stringify(service_runtime.get("launchMode") or "docker"),
        "EASYBROWSER_DOCKER_NETWORK": stringify(service_runtime.get("dockerNetwork") or "EasyAiMi"),
        "EASYBROWSER_DOCKER_COMPOSE_PROJECT": stringify(service_runtime.get("dockerComposeProject") or "easy-browser"),
        "EASYBROWSER_CHROME_DOCKER_IMAGE": stringify((chrome.get("dockerImage") or "easy-browser/chrome-runtime:local")),
        "EASYBROWSER_CAMOUFOX_DOCKER_IMAGE": stringify((camoufox.get("dockerImage") or "easy-browser/camoufox-runtime:local")),
        "EASYBROWSER_GEEKEZ_DOCKER_IMAGE": stringify((geekez.get("dockerImage") or "easy-browser/geekez-runtime:local")),
        "EASYBROWSER_CHROME_HEADLESS": "1" if normalize_bool(chrome.get("headless"), True) else "0",
        "EASYBROWSER_CHROME_USE_UNDETECTED_CHROMEDRIVER": "1"
        if normalize_bool(chrome.get("useUndetectedChromedriver"), False)
        else "0",
        "EASYBROWSER_CAMOUFOX_HEADLESS": "1" if normalize_bool(camoufox.get("headless"), True) else "0",
        "EASYBROWSER_RUNTIME_POOL_ENABLED": "1" if normalize_bool(runtime_pool.get("enabled"), True) else "0",
        "EASYBROWSER_RUNTIME_POOL_RECONCILE_SECONDS": stringify(runtime_pool.get("reconcileSeconds") or 5),
        "EASYBROWSER_RUNTIME_POOL_IDLE_TIMEOUT_SECONDS": stringify(runtime_pool.get("idleTimeoutSeconds") or 120),
        "EASYBROWSER_CHROME_MIN_WARM": stringify((runtime_pool_providers.get("chrome") or {}).get("minWarm") or 1),
        "EASYBROWSER_CAMOUFOX_MIN_WARM": stringify((runtime_pool_providers.get("camoufox") or {}).get("minWarm") or 0),
        "EASYBROWSER_GEEKEZ_MIN_WARM": stringify((runtime_pool_providers.get("geekez") or {}).get("minWarm") or 0),
        "EASYBROWSER_BROWSERBASE_MIN_WARM": stringify((runtime_pool_providers.get("browserbase") or {}).get("minWarm") or 0),
    }

    optional_map = {
        "EASYBROWSER_CHROME_BINARY_PATH": chrome.get("binaryPath"),
        "EASYBROWSER_CHROMEDRIVER_PATH": chrome.get("chromedriverPath"),
        "EASYBROWSER_CHROME_PYTHON": chrome.get("pythonPath"),
        "EASYBROWSER_CAMOUFOX_PYTHON": camoufox.get("pythonPath"),
        "EASYBROWSER_CAMOUFOX_OS": camoufox.get("os"),
        "EASYBROWSER_CAMOUFOX_READY_TIMEOUT_MS": camoufox.get("readyTimeoutMs"),
        "EASYBROWSER_GEEKEZ_PYTHON": geekez.get("pythonPath"),
        "EASYBROWSER_GEEKEZ_READY_TIMEOUT_MS": geekez.get("readyTimeoutMs"),
        "BROWSERBASE_API_KEY": browserbase.get("apiKey"),
        "BROWSERBASE_PROJECT_ID": browserbase.get("projectId"),
    }

    for key, value in optional_map.items():
        text = stringify(value)
        if text:
            env[key] = text

    return env


def write_env_file(path: Path, values: dict[str, str]) -> None:
    lines = [f"{key}={value}" for key, value in values.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render derived EasyBrowser runtime configuration files.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--service-output", default="")
    parser.add_argument("--service-env-output", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_yaml_file(config_path)

    if args.service_output:
        service_output = Path(args.service_output).resolve()
        service_output.parent.mkdir(parents=True, exist_ok=True)
        service_output.write_text(
            yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    runtime_env = build_runtime_env(config)
    runtime_env_output = Path(args.service_env_output).resolve()
    write_env_file(runtime_env_output, runtime_env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
