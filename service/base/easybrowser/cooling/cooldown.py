from __future__ import annotations

import dataclasses
import time

from .affinity import AffinityRecord


@dataclasses.dataclass
class CooldownConfig:
    """Configuration for cooldown behavior."""

    failure_threshold: int = 3
    """Number of consecutive failures before triggering cooldown."""

    base_cooldown_seconds: float = 60.0
    """Base cooldown duration in seconds (first cooldown)."""

    max_cooldown_seconds: float = 3600.0
    """Maximum cooldown duration in seconds (cap for exponential backoff)."""

    decay_after_seconds: float = 1800.0
    """After this many seconds of inactivity, reduce recent_failures by 1 on recovery."""


class CooldownPolicy:
    """Determines when to cool a provider and how long the cooldown lasts.

    Follows the pattern from EasyEmail's provider-operational-state.ts:
    - Trigger when recent_failures >= threshold
    - Exponential backoff: base * 2^(cool_count-1), capped at max
    - Auto-recover when cooldown expires
    - Force-release all when every provider is cooled (EasyProxy pattern)
    """

    def __init__(self, config: CooldownConfig | None = None) -> None:
        self._config = config or CooldownConfig()

    @property
    def config(self) -> CooldownConfig:
        return self._config

    def should_cool(self, record: AffinityRecord) -> bool:
        if record.is_cooled:
            return False
        return record.recent_failures >= self._config.failure_threshold

    def compute_cooldown_duration(self, record: AffinityRecord) -> float:
        exponent = max(0, record.cool_count)
        duration = self._config.base_cooldown_seconds * (2 ** exponent)
        return min(duration, self._config.max_cooldown_seconds)

    def apply_cooldown(self, record: AffinityRecord) -> AffinityRecord:
        """Apply cooldown to a record. Returns a new record with cooled_until set."""
        duration = self.compute_cooldown_duration(record)
        return dataclasses.replace(
            record,
            cooled_until=time.time() + duration,
            cool_count=record.cool_count + 1,
        )

    def try_recover(self, record: AffinityRecord) -> AffinityRecord:
        """If cooldown has expired, recover the record."""
        if record.cooled_until <= 0:
            return record
        if time.time() < record.cooled_until:
            return record
        return dataclasses.replace(
            record,
            cooled_until=0.0,
            recent_failures=0,
        )

    def force_release_all(self, records: list[AffinityRecord]) -> list[AffinityRecord]:
        """Force-release all cooled records (used when all providers are cooled)."""
        return [
            dataclasses.replace(r, cooled_until=0.0, recent_failures=0)
            for r in records
        ]
