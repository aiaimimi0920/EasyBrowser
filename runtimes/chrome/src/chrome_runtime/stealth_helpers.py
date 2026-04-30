from __future__ import annotations

import os
import re
from typing import Any


def env_flag(name: str, default: str = "1") -> bool:
    return (os.environ.get(name, default) or default).strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def build_greased_brands(major_version: int) -> list[dict[str, str]]:
    order = [
        [0, 1, 2],
        [0, 2, 1],
        [1, 0, 2],
        [1, 2, 0],
        [2, 0, 1],
        [2, 1, 0],
    ][major_version % 6]
    escaped_chars = [" ", " ", ";"]
    grease_brand = f"{escaped_chars[order[0]]}Not{escaped_chars[order[1]]}A{escaped_chars[order[2]]}Brand"
    brands: list[dict[str, str]] = [
        {"brand": grease_brand, "version": "99"},
        {"brand": "Chromium", "version": str(major_version)},
        {"brand": "Google Chrome", "version": str(major_version)},
    ]
    return [brands[index] for index in order]


def extract_user_agent_bits(user_agent: str) -> dict[str, Any]:
    ua = str(user_agent or "")
    full_version = "120.0.0.0"
    match = re.search(r"Chrome/([\d.]+)", ua)
    if match:
        full_version = match.group(1)
    try:
        major_version = max(int(full_version.split(".", 1)[0]), 1)
    except Exception:
        major_version = 120
        full_version = "120.0.0.0"

    mobile = "Android" in ua or "Mobile" in ua
    if "Windows" in ua:
        platform_short = "Win32"
        platform_name = "Windows"
        platform_match = re.search(r"Windows NT ([\d.]+)", ua)
        platform_version = platform_match.group(1) if platform_match else "10.0"
        architecture = "x86"
        model = ""
    elif "Mac OS X" in ua:
        platform_short = "MacIntel"
        platform_name = "macOS"
        platform_match = re.search(r"Mac OS X ([^;)]+)", ua)
        platform_version = platform_match.group(1) if platform_match else "10_15_7"
        architecture = "x86"
        model = ""
    elif "Android" in ua:
        platform_short = "Android"
        platform_name = "Android"
        platform_match = re.search(r"Android ([^;)]+)", ua)
        platform_version = platform_match.group(1) if platform_match else "12"
        architecture = ""
        model_match = re.search(r"Android [^;]+;\s*([^)]+)", ua)
        model = model_match.group(1) if model_match else ""
    elif "Linux" in ua:
        platform_short = "Linux x86_64"
        platform_name = "Linux"
        platform_version = ""
        architecture = "x86"
        model = ""
    else:
        platform_short = "Win32"
        platform_name = "Windows"
        platform_version = "10.0"
        architecture = "x86"
        model = ""

    brands = build_greased_brands(major_version)
    full_version_list = [
        {
            "brand": item["brand"],
            "version": full_version if item["brand"] != brands[0]["brand"] else "99.0.0.0",
        }
        for item in brands
    ]
    return {
        "userAgent": ua,
        "fullVersion": full_version,
        "majorVersion": major_version,
        "platformShort": platform_short,
        "platformName": platform_name,
        "platformVersion": platform_version,
        "architecture": architecture,
        "model": model,
        "mobile": mobile,
        "brands": brands,
        "fullVersionList": full_version_list,
    }
