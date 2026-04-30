from __future__ import annotations

from typing import Any

from .affinity import AffinityRecord, AffinityTracker
from .cooldown import CooldownPolicy


class AffinityRouter:
    """Selects the best provider for a task based on historical affinity scores.

    Core logic:
    1. If caller specifies a provider, use it directly
    2. Otherwise, get all providers' affinity scores for this task_type
    3. Filter out cooled providers (unless ALL are cooled → force-release all)
    4. Return the provider with the highest score

    After each task execution, call record_result() to update the scores.
    """

    def __init__(
        self,
        tracker: AffinityTracker | None = None,
        policy: CooldownPolicy | None = None,
        providers: list[str] | None = None,
    ) -> None:
        self._tracker = tracker or AffinityTracker()
        self._policy = policy or CooldownPolicy()
        self._providers = list(providers or [])

    @property
    def tracker(self) -> AffinityTracker:
        return self._tracker

    @property
    def policy(self) -> CooldownPolicy:
        return self._policy

    @property
    def providers(self) -> list[str]:
        return list(self._providers)

    def select_provider(self, task_type: str, preferred: str | None = None) -> str:
        """Select the best provider for a task_type.

        Args:
            task_type: The task type to route.
            preferred: If set, use this provider directly (bypass affinity).

        Returns:
            The selected provider name.
        """
        if preferred:
            return preferred

        if not self._providers:
            return "chrome"

        # Recover any expired cooldowns
        for provider in self._providers:
            record = self._tracker.get_record(task_type, provider)
            recovered = self._policy.try_recover(record)
            if recovered is not record and recovered.cooled_until != record.cooled_until:
                self._tracker.update_record(recovered)

        # Score all providers
        scored: list[tuple[str, float, bool]] = []
        for provider in self._providers:
            record = self._tracker.get_record(task_type, provider)
            scored.append((provider, record.score, record.is_cooled))

        # Check if all are cooled
        all_cooled = all(cooled for _, _, cooled in scored)
        if all_cooled and len(scored) > 0:
            records = [self._tracker.get_record(task_type, p) for p in self._providers]
            released = self._policy.force_release_all(records)
            for r in released:
                self._tracker.update_record(r)
            # Re-score after release
            scored = []
            for provider in self._providers:
                record = self._tracker.get_record(task_type, provider)
                scored.append((provider, record.score, record.is_cooled))

        # Filter out cooled, sort by score descending
        available = [(p, s) for p, s, cooled in scored if not cooled]
        if not available:
            available = [(p, s) for p, s, _ in scored]

        available.sort(key=lambda x: x[1], reverse=True)
        return available[0][0]

    def record_result(self, task_type: str, provider: str, success: bool) -> AffinityRecord:
        """Record a task result and apply cooldown if needed.

        Args:
            task_type: The task type that was executed.
            provider: The provider that executed it.
            success: Whether the execution succeeded.

        Returns:
            The updated AffinityRecord.
        """
        if success:
            record = self._tracker.record_success(task_type, provider)
        else:
            record = self._tracker.record_failure(task_type, provider)
            if self._policy.should_cool(record):
                record = self._policy.apply_cooldown(record)
                self._tracker.update_record(record)

        return record

    def get_rankings(self, task_type: str) -> list[tuple[str, float, bool]]:
        """Get provider rankings for a task_type.

        Returns:
            List of (provider, score, is_cooled) sorted by score descending.
        """
        # Recover expired cooldowns first
        for provider in self._providers:
            record = self._tracker.get_record(task_type, provider)
            recovered = self._policy.try_recover(record)
            if recovered is not record and recovered.cooled_until != record.cooled_until:
                self._tracker.update_record(recovered)

        rankings: list[tuple[str, float, bool]] = []
        for provider in self._providers:
            record = self._tracker.get_record(task_type, provider)
            rankings.append((provider, record.score, record.is_cooled))

        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings

    def get_stats(self) -> list[dict[str, Any]]:
        """Get all affinity records as dicts for inspection."""
        return [r.to_dict() for r in self._tracker.get_all_records()]

    def reset_all(self) -> None:
        """Reset all affinity tracking data."""
        self._tracker.reset()
