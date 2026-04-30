from __future__ import annotations

import dataclasses
import threading
import time
from typing import Any


@dataclasses.dataclass
class AffinityRecord:
    """Tracks the affinity between a (task_type, provider) pair.

    A higher score means the provider is better suited for the task.
    Score is computed from success rate minus failure penalties and cooling state.
    """

    task_type: str
    provider: str
    successes: int = 0
    failures: int = 0
    recent_failures: int = 0
    cooled_until: float = 0.0
    cool_count: int = 0
    last_result_at: float = 0.0

    @property
    def total(self) -> int:
        return self.successes + self.failures

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.successes / self.total

    @property
    def is_cooled(self) -> bool:
        return self.cooled_until > 0 and time.time() < self.cooled_until

    @property
    def score(self) -> float:
        if self.is_cooled:
            return -1000.0
        if self.total == 0:
            return 0.0
        return 100.0 * self.success_rate - self.recent_failures * 30.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "provider": self.provider,
            "successes": self.successes,
            "failures": self.failures,
            "recent_failures": self.recent_failures,
            "cooled_until": self.cooled_until,
            "cool_count": self.cool_count,
            "last_result_at": self.last_result_at,
            "total": self.total,
            "success_rate": round(self.success_rate, 4),
            "is_cooled": self.is_cooled,
            "score": round(self.score, 2),
        }


class AffinityTracker:
    """Thread-safe tracker for (task_type, provider) affinity records."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], AffinityRecord] = {}
        self._lock = threading.Lock()

    def _key(self, task_type: str, provider: str) -> tuple[str, str]:
        return (task_type, provider)

    def get_record(self, task_type: str, provider: str) -> AffinityRecord:
        key = self._key(task_type, provider)
        with self._lock:
            record = self._records.get(key)
            if record is None:
                record = AffinityRecord(task_type=task_type, provider=provider)
                self._records[key] = record
            return dataclasses.replace(record)

    def record_success(self, task_type: str, provider: str) -> AffinityRecord:
        key = self._key(task_type, provider)
        now = time.time()
        with self._lock:
            record = self._records.get(key)
            if record is None:
                record = AffinityRecord(task_type=task_type, provider=provider)
                self._records[key] = record
            record.successes += 1
            record.recent_failures = 0
            record.last_result_at = now
            return dataclasses.replace(record)

    def record_failure(self, task_type: str, provider: str) -> AffinityRecord:
        key = self._key(task_type, provider)
        now = time.time()
        with self._lock:
            record = self._records.get(key)
            if record is None:
                record = AffinityRecord(task_type=task_type, provider=provider)
                self._records[key] = record
            record.failures += 1
            record.recent_failures += 1
            record.last_result_at = now
            return dataclasses.replace(record)

    def update_record(self, record: AffinityRecord) -> None:
        """Write back a modified record (e.g., after cooldown applied)."""
        key = self._key(record.task_type, record.provider)
        with self._lock:
            self._records[key] = record

    def get_records_for_task(self, task_type: str) -> list[AffinityRecord]:
        with self._lock:
            return [
                dataclasses.replace(r)
                for r in self._records.values()
                if r.task_type == task_type
            ]

    def get_all_records(self) -> list[AffinityRecord]:
        with self._lock:
            return [dataclasses.replace(r) for r in self._records.values()]

    def reset(self, task_type: str | None = None, provider: str | None = None) -> None:
        with self._lock:
            if task_type is None and provider is None:
                self._records.clear()
                return
            keys_to_remove = [
                k for k in self._records
                if (task_type is None or k[0] == task_type)
                and (provider is None or k[1] == provider)
            ]
            for k in keys_to_remove:
                del self._records[k]
