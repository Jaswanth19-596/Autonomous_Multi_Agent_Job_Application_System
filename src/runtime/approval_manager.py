"""One-shot approval futures for human-in-the-loop tool execution."""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    id: str
    tool_calls: tuple[dict[str, Any], ...]


class ApprovalManager:
    def __init__(self) -> None:
        self._requests: dict[str, asyncio.Future[bool]] = {}

    def create_request(self, tool_calls: list[dict[str, Any]]) -> ApprovalRequest:
        approval_id = uuid.uuid4().hex
        self._requests[approval_id] = asyncio.get_running_loop().create_future()
        return ApprovalRequest(approval_id, tuple(tool_calls))

    async def wait_for(self, approval_id: str, timeout: float | None = None) -> bool | None:
        future = self._requests.get(approval_id)
        if future is None:
            return None
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout) if timeout else await future
        except asyncio.TimeoutError:
            return None
        finally:
            self._requests.pop(approval_id, None)

    def resolve(self, approval_id: str, approved: bool) -> bool:
        future = self._requests.get(approval_id)
        if future is None or future.done():
            return False
        future.set_result(approved)
        return True
