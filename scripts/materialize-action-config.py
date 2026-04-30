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
    ghcr_image_name = os.environ.get("EASYBROWSER_GHCR_IMAGE_NAME", "").strip()
    ghcr_namespace = os.environ.get("EASYBROWSER_GHCR_NAMESPACE", "").strip()
    ghcr_registry = os.environ.get("EASYBROWSER_GHCR_REGISTRY", "").strip()

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

    if ghcr_image_name:
        overlay.setdefault("publishing", {}).setdefault("ghcr", {})["imageName"] = ghcr_image_name
    if ghcr_namespace:
        overlay.setdefault("publishing", {}).setdefault("ghcr", {})["namespace"] = ghcr_namespace
    if ghcr_registry:
        overlay.setdefault("publishing", {}).setdefault("ghcr", {})["registry"] = ghcr_registry

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
