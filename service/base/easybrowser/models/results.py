from __future__ import annotations

import dataclasses
from typing import Any

from .options import FingerprintConfig


@dataclasses.dataclass
class PageInfo:
    url: str = ""
    title: str = ""


@dataclasses.dataclass
class TaskConfig:
    task_type: str
    provider: str | None = None
    proxy: str | None = None
    fingerprint: FingerprintConfig | None = None
    params: dict[str, Any] = dataclasses.field(default_factory=dict)
    timeout_ms: int = 120000


@dataclasses.dataclass
class TaskResult:
    success: bool
    task_type: str
    provider: str
    data: dict[str, Any] = dataclasses.field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0
