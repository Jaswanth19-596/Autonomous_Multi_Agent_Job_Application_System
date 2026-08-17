import asyncio

from src.core.logging import redact_sensitive
from src.notifications.event_bus import AgentEventBus
from src.notifications.telegram_formatter import split_telegram_text
from src.notifications.telegram_formatter import format_event
from src.notifications.events import AgentEvent
from src.notifications.telegram_service import TelegramConfig, TelegramService
from src.runtime.approval_manager import ApprovalManager
from src.runtime.controller import AgentRuntimeController
from src.runtime.input_manager import AgentInputManager
from src.runtime.services import AgentRuntime


def test_event_bus_delivers_and_isolates_failing_subscribers():
    async def scenario():
        bus = AgentEventBus()
        received = []

        async def good(event):
            received.append(event.type)

        async def bad(event):
            raise RuntimeError("offline notifier")

        bus.subscribe(good)
        bus.subscribe(bad)
        await bus.emit("tool.started", {"tool": "browser"})
        assert received == ["tool.started"]

    asyncio.run(scenario())


def test_approval_is_one_shot_and_ids_do_not_cross_resolve():
    async def scenario():
        manager = ApprovalManager()
        first = manager.create_request([{"name": "send_email"}])
        second = manager.create_request([{"name": "terminal"}])
        wait_first = asyncio.create_task(manager.wait_for(first.id))
        assert not manager.resolve("not-an-id", True)
        assert manager.resolve(second.id, True)
        assert manager.resolve(first.id, False)
        assert not manager.resolve(first.id, True)
        assert await wait_first is False
        assert await manager.wait_for(second.id) is True

    asyncio.run(scenario())


def test_pending_question_resolves_once_and_other_messages_queue():
    async def scenario():
        manager = AgentInputManager()
        pending = manager.create_question("Salary?", ["100k", "120k"])
        wait_answer = asyncio.create_task(manager.wait_for_question(pending.id))
        assert manager.resolve_question_option(pending.id, 1)
        assert not manager.resolve_question_option(pending.id, 0)
        assert await wait_answer == "120k"
        assert not await manager.submit_message("next task")
        assert await manager.messages.get() == "next task"

    asyncio.run(scenario())


def test_pause_resume_and_stop_are_event_based():
    async def scenario():
        controller = AgentRuntimeController()
        await controller.start()
        assert await controller.pause()
        waiter = asyncio.create_task(controller.wait_if_paused())
        await asyncio.sleep(0)
        assert not waiter.done()
        assert await controller.resume()
        assert await waiter
        assert await controller.stop()
        assert controller.snapshot().status == "stopped"
        assert not await controller.wait_if_paused()

    asyncio.run(scenario())


def test_telegram_rejects_unauthorized_updates():
    class FakeTelegram(TelegramService):
        def __init__(self, config, runtime):
            super().__init__(config, runtime)
            self.calls = []

        async def _call(self, method, payload, timeout=15):
            self.calls.append((method, payload))
            return []

    async def scenario():
        service = FakeTelegram(TelegramConfig("test-token", 42, True), AgentRuntime())
        await service.handle_update({"message": {"chat": {"id": 99}, "text": "/status"}})
        assert service.calls == []

    asyncio.run(scenario())


def test_telegram_start_recovers_a_stopping_agent_and_leaves_messages_usable():
    class FakeTelegram(TelegramService):
        def __init__(self, config, runtime):
            super().__init__(config, runtime)
            self.messages = []

        async def _send_direct(self, text, keyboard=None):
            self.messages.append((text, keyboard))

    async def scenario():
        runtime = AgentRuntime()
        await runtime.controller.start("old task")
        assert await runtime.controller.stop()
        service = FakeTelegram(TelegramConfig("test-token", 42, True), runtime)

        await service._handle_message("/start")

        assert runtime.controller.snapshot().status == "running"
        assert service.messages[0][0].startswith("🤖 Agent started")
        await service._handle_message("Hey")
        assert await runtime.inputs.messages.get() == "Hey"

    asyncio.run(scenario())


def test_telegram_stop_reports_stopped_and_offers_start():
    class FakeTelegram(TelegramService):
        def __init__(self, config, runtime):
            super().__init__(config, runtime)
            self.messages = []

        async def _send_direct(self, text, keyboard=None):
            self.messages.append((text, keyboard))

    async def scenario():
        runtime = AgentRuntime()
        await runtime.controller.start()
        service = FakeTelegram(TelegramConfig("test-token", 42, True), runtime)

        await service._handle_message("/stop")
        await service._handle_message("/status")

        assert runtime.controller.snapshot().status == "stopped"
        assert service.messages[0][0].startswith("🛑 Agent stopped")
        assert service.messages[1][0].startswith("Agent: Stopped")
        assert service.messages[1][1] == [[{"text": "▶️ Start", "callback_data": "command:start"}]]

    asyncio.run(scenario())


def test_redaction_and_telegram_splitting_are_safe():
    redacted = redact_sensitive({"api_key": "secret", "nested": "token=abc"})
    assert redacted["api_key"] == "[REDACTED]"
    assert "abc" not in redacted["nested"]
    chunks = split_telegram_text("x" * 9001)
    assert len(chunks) == 3
    assert all(len(chunk) <= 4000 for chunk in chunks)


def test_job_finished_notification_includes_outcome_and_efficiency_metrics():
    message = format_event(AgentEvent("job.finished", {
        "company": "Acme",
        "title": "AI Engineer",
        "status": "applied",
        "metrics": {
            "application_duration_seconds": 125.2,
            "application_tool_calls": 17,
            "application_cost_usd": 0.0135,
        },
    }))

    assert message is not None
    assert "Status: Applied" in message.text
    assert "Duration: 2m 5s" in message.text
    assert "Tool calls: 17" in message.text
    assert "Model cost: $0.013500" in message.text
