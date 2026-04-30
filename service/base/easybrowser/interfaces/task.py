from __future__ import annotations

from abc import ABC, abstractmethod

from ..models.results import TaskConfig, TaskResult


class TaskExecutor(ABC):
    """High-level task execution interface."""

    @abstractmethod
    async def execute_task(self, config: TaskConfig) -> TaskResult: ...

    @abstractmethod
    async def cancel_task(self, task_id: str) -> bool: ...

    @abstractmethod
    def supported_task_types(self) -> list[str]: ...
