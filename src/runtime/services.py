"""The small, explicit service bundle used by LangGraph nodes."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.notifications.event_bus import AgentEventBus
from src.runtime.approval_manager import ApprovalManager
from src.runtime.controller import AgentRuntimeController
from src.runtime.input_manager import AgentInputManager


@dataclass(slots=True)
class AgentRuntime:
    events: AgentEventBus = field(default_factory=AgentEventBus)
    controller: AgentRuntimeController = field(default_factory=AgentRuntimeController)
    approvals: ApprovalManager = field(default_factory=ApprovalManager)
    inputs: AgentInputManager = field(default_factory=AgentInputManager)


_runtime: AgentRuntime | None = None


def configure_runtime(runtime: AgentRuntime) -> None:
    global _runtime
    _runtime = runtime


def get_runtime() -> AgentRuntime:
    global _runtime
    if _runtime is None:
        _runtime = AgentRuntime()
    return _runtime
