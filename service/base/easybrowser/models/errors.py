from __future__ import annotations


class EasyBrowserError(Exception):
    def __init__(
        self,
        message: str,
        *,
        category: str = "unknown",
        code: str = "unknown_error",
        retriable: bool = False,
        cooldown_candidate: bool = False,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.code = code
        self.retriable = retriable
        self.cooldown_candidate = cooldown_candidate


class ProviderNotFoundError(EasyBrowserError):
    def __init__(self, message: str) -> None:
        super().__init__(message, category="config", code="provider_not_found")


class NavigationError(EasyBrowserError):
    def __init__(self, message: str, *, retriable: bool = False) -> None:
        super().__init__(message, category="navigation", code="navigation_error", retriable=retriable)


class ElementNotFoundError(EasyBrowserError):
    def __init__(self, message: str) -> None:
        super().__init__(message, category="element", code="element_not_found")


class TimeoutError(EasyBrowserError):
    def __init__(self, message: str, *, retriable: bool = True) -> None:
        super().__init__(message, category="timeout", code="timeout", retriable=retriable)


class ConnectionError(EasyBrowserError):
    def __init__(self, message: str, *, retriable: bool = True) -> None:
        super().__init__(
            message,
            category="connection",
            code="connection_error",
            retriable=retriable,
            cooldown_candidate=True,
        )
