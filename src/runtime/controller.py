"""Concurrency-safe control plane for a running agent."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    status: str
    current_task: str | None
    current_operation: str | None
    current_tool: str | None
    progress_current: int | None
    progress_total: int | None
    started_at: datetime | None


class AgentRuntimeController:
    """Coordinate pause/resume/stop at safe graph and tool boundaries."""

    def __init__(self) -> None:
        self._resume_event = asyncio.Event()
        self._resume_event.set()
        self._status = "idle"
        self._current_task: str | None = None
        self._current_operation: str | None = None
        self._current_tool: str | None = None
        self._progress_current: int | None = None
        self._progress_total: int | None = None
        self._started_at: datetime | None = None

    async def start(self, task: str | None = None) -> None:
        self._status = "running"
        self._current_task = task
        self._current_operation = None
        self._current_tool = None
        self._progress_current = None
        self._progress_total = None
        self._started_at = datetime.now(timezone.utc)
        self._resume_event.set()

    async def complete(self) -> None:
        self._status = "completed"
        self._current_tool = None
        self._current_operation = None
        self._resume_event.set()

    async def pause(self) -> bool:
        if self._status not in {"running", "paused"}:
            return False
        self._status = "paused"
        self._resume_event.clear()
        return True

    async def resume(self) -> bool:
        if self._status != "paused":
            return False
        self._status = "running"
        self._resume_event.set()
        return True

    async def stop(self) -> bool:
        if self._status not in {"running", "paused"}:
            return False
        self._status = "stopped"
        self._current_task = None
        self._current_operation = None
        self._current_tool = None
        self._progress_current = None
        self._progress_total = None
        self._resume_event.set()
        return True

    async def wait_if_paused(self) -> bool:
        """Wait without polling. False means no further operation should start."""
        await self._resume_event.wait()
        return self._status not in {"stopping", "stopped"}

    @property
    def stopping(self) -> bool:
        return self._status in {"stopping", "stopped"}

    async def set_task(self, task: str | None, operation: str | None = None) -> None:
        self._current_task = task
        if operation is not None:
            self._current_operation = operation

    async def set_tool(self, tool: str | None) -> None:
        self._current_tool = tool

    async def set_progress(self, current: int | None, total: int | None) -> None:
        self._progress_current = current
        self._progress_total = total

    def snapshot(self) -> RuntimeSnapshot:
        return RuntimeSnapshot(
            status=self._status,
            current_task=self._current_task,
            current_operation=self._current_operation,
            current_tool=self._current_tool,
            progress_current=self._progress_current,
            progress_total=self._progress_total,
            started_at=self._started_at,
        )
