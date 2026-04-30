#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re


SERVICE_BASE_PATTERNS = [
    re.compile(r"^v.+$"),
    re.compile(r"^release-.+$"),
    re.compile(r"^service-base-.+$"),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()

    if args.mode != "service-base":
        raise SystemExit(f"Unsupported mode: {args.mode}")

    if any(pattern.match(args.tag) for pattern in SERVICE_BASE_PATTERNS):
        return

    raise SystemExit(
        "Unsupported release tag. Expected one of: v*, release-*, service-base-*"
    )


if __name__ == "__main__":
    main()
