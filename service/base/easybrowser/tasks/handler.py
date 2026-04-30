from __future__ import annotations

from abc import ABC, abstractmethod

from ..interfaces.page import BrowserPage
from ..models.results import TaskConfig, TaskResult


class TaskHandler(ABC):
    """Base class for task handlers.

    Each handler implements the business logic for a specific task_type,
    using the unified BrowserPage interface.
    """

    @abstractmethod
    async def run(self, page: BrowserPage, config: TaskConfig) -> TaskResult: ...
