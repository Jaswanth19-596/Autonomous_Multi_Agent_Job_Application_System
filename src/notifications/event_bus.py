"""Best-effort asynchronous event fan-out."""
from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from src.notifications.events import AgentEvent

logger = logging.getLogger(__name__)
Subscriber = Callable[[AgentEvent], Awaitable[None] | None]


class AgentEventBus:
    """Deliver events to independent subscribers without coupling producers to UI."""

    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []

    def subscribe(self, subscriber: Subscriber) -> None:
        if subscriber not in self._subscribers:
            self._subscribers.append(subscriber)

    def unsubscribe(self, subscriber: Subscriber) -> None:
        if subscriber in self._subscribers:
            self._subscribers.remove(subscriber)

    async def emit(self, event: AgentEvent | str, data: dict[str, Any] | None = None) -> AgentEvent:
        emitted = event if isinstance(event, AgentEvent) else AgentEvent(event, data or {})
        if not self._subscribers:
            return emitted

        results = await asyncio.gather(
            *(self._deliver(subscriber, emitted) for subscriber in tuple(self._subscribers)),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Agent event subscriber failed: %s", result)
        return emitted

    @staticmethod
    async def _deliver(subscriber: Subscriber, event: AgentEvent) -> None:
        result: Any = subscriber(event)
        if inspect.isawaitable(result):
            await result
