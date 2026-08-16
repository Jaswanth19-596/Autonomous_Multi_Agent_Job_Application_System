"""Queues remote messages and resolves one pending agent question safely."""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PendingQuestion:
    id: str
    question: str
    options: tuple[str, ...]


class AgentInputManager:
    def __init__(self) -> None:
        self.messages: asyncio.Queue[str] = asyncio.Queue()
        self._question_id: str | None = None
        self._question_options: tuple[str, ...] = ()
        self._question_future: asyncio.Future[str] | None = None

    async def submit_message(self, message: str) -> bool:
        """Resolve a pending question first; otherwise queue it for the manager graph."""
        if self._question_future is not None and not self._question_future.done():
            self._question_future.set_result(message)
            return True
        await self.messages.put(message)
        return False

    def create_question(self, question: str, options: list[str] | None = None) -> PendingQuestion:
        if self._question_future is not None and not self._question_future.done():
            raise RuntimeError("An agent question is already waiting for an answer.")
        self._question_id = uuid.uuid4().hex
        self._question_options = tuple(options or ())
        self._question_future = asyncio.get_running_loop().create_future()
        return PendingQuestion(self._question_id, question, self._question_options)

    def resolve_question_option(self, question_id: str, option_index: int) -> bool:
        if question_id != self._question_id or self._question_future is None or self._question_future.done():
            return False
        if option_index < 0 or option_index >= len(self._question_options):
            return False
        self._question_future.set_result(self._question_options[option_index])
        return True

    async def wait_for_question(self, question_id: str, timeout: float | None = None) -> str | None:
        if question_id != self._question_id or self._question_future is None:
            return None
        future = self._question_future
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout) if timeout else await future
        except asyncio.TimeoutError:
            return None
        finally:
            if self._question_id == question_id:
                self._question_id = None
                self._question_options = ()
                self._question_future = None
