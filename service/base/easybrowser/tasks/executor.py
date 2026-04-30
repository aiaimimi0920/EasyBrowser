from __future__ import annotations

import time
from typing import Any

from ..cooling.router import AffinityRouter
from ..interfaces.provider import BrowserProvider
from ..interfaces.task import TaskExecutor
from ..models.errors import EasyBrowserError, ProviderNotFoundError
from ..models.options import LaunchOptions, ProxyConfig
from ..models.results import TaskConfig, TaskResult
from ..providers.registry import create_provider, list_providers
from .handler import TaskHandler


class DefaultTaskExecutor(TaskExecutor):
    """Task executor with built-in affinity-based provider routing.

    When config.provider is not specified, the executor automatically selects
    the best provider based on historical success/failure rates per task_type.

    Providers that fail repeatedly for a given task_type get cooled down
    (temporarily deprioritized). The system auto-recovers cooled providers
    after the cooldown window expires.

    Usage::

        executor = DefaultTaskExecutor()
        executor.register_handler("navigate", NavigateHandler())

        # Provider auto-selected based on affinity
        result = await executor.execute_task(TaskConfig(
            task_type="navigate",
            params={"url": "https://example.com"},
        ))

        # Or pin a specific provider
        result = await executor.execute_task(TaskConfig(
            task_type="navigate",
            provider="chrome",
            params={"url": "https://example.com"},
        ))
    """

    def __init__(
        self,
        providers: dict[str, BrowserProvider] | None = None,
        *,
        router: AffinityRouter | None = None,
        enable_affinity: bool = True,
    ) -> None:
        self._providers: dict[str, BrowserProvider] = dict(providers or {})
        self._handlers: dict[str, TaskHandler] = {}
        self._active_tasks: dict[str, str] = {}
        self._enable_affinity = enable_affinity
        self._router = router or AffinityRouter(providers=list_providers())

    @property
    def router(self) -> AffinityRouter:
        """Access the affinity router for inspection or configuration."""
        return self._router

    def register_handler(self, task_type: str, handler: TaskHandler) -> None:
        self._handlers[task_type] = handler

    def register_provider(self, name: str, provider: BrowserProvider) -> None:
        self._providers[name] = provider

    async def execute_task(self, config: TaskConfig) -> TaskResult:
        start = time.monotonic()
        handler = self._handlers.get(config.task_type)
        if handler is None:
            raise ProviderNotFoundError(f"No handler registered for task type: {config.task_type!r}")

        # Select provider: explicit > affinity router > default
        if self._enable_affinity:
            provider_name = self._router.select_provider(
                config.task_type, config.provider
            )
        else:
            provider_name = config.provider or "chrome"

        provider = self._providers.get(provider_name)
        if provider is None:
            provider = create_provider(provider_name)
            self._providers[provider_name] = provider

        proxy_config: ProxyConfig | None = None
        if config.proxy:
            proxy_config = ProxyConfig(server=config.proxy)

        launch_opts = LaunchOptions(
            proxy=proxy_config,
            fingerprint=config.fingerprint,
        )

        context = await provider.launch(launch_opts)
        try:
            page = await context.new_page()
            try:
                result = await handler.run(page, config)
                result.duration_ms = int((time.monotonic() - start) * 1000)
                result.provider = provider_name

                # Record result for affinity tracking
                if self._enable_affinity:
                    self._router.record_result(config.task_type, provider_name, result.success)

                return result
            except EasyBrowserError as exc:
                if self._enable_affinity:
                    self._router.record_result(config.task_type, provider_name, False)
                return TaskResult(
                    success=False,
                    task_type=config.task_type,
                    provider=provider_name,
                    error=str(exc),
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            except Exception as exc:
                if self._enable_affinity:
                    self._router.record_result(config.task_type, provider_name, False)
                return TaskResult(
                    success=False,
                    task_type=config.task_type,
                    provider=provider_name,
                    error=str(exc),
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            finally:
                await page.close()
        finally:
            await context.close()

    async def cancel_task(self, task_id: str) -> bool:
        return self._active_tasks.pop(task_id, None) is not None

    def supported_task_types(self) -> list[str]:
        return sorted(self._handlers.keys())

    def get_affinity_stats(self) -> list[dict[str, Any]]:
        """Get all affinity tracking data for inspection."""
        return self._router.get_stats()

    def get_rankings(self, task_type: str) -> list[tuple[str, float, bool]]:
        """Get provider rankings for a specific task type."""
        return self._router.get_rankings(task_type)
