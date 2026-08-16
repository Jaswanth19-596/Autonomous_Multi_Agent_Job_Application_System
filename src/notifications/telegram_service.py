"""Minimal asyncio-compatible Telegram Bot API subscriber and control surface."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from src.notifications.events import AgentEvent
from src.notifications.telegram_formatter import TelegramMessage, format_event, split_telegram_text
from src.runtime.services import AgentRuntime

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TelegramConfig:
    token: str
    allowed_chat_id: int
    enabled: bool

    @classmethod
    def from_env(cls) -> "TelegramConfig | None":
        enabled = os.environ.get("TELEGRAM_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
        if not enabled:
            return None
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.environ.get("TELEGRAM_ALLOWED_CHAT_ID", "").strip()
        if not token:
            logger.warning("Telegram is enabled but TELEGRAM_BOT_TOKEN is missing; integration is disabled.")
            return None
        try:
            return cls(token=token, allowed_chat_id=int(chat_id), enabled=True)
        except ValueError:
            logger.warning("Telegram is enabled but TELEGRAM_ALLOWED_CHAT_ID is invalid; integration is disabled.")
            return None


class TelegramService:
    """Queues notifications and long-polls controls without blocking LangGraph."""

    def __init__(self, config: TelegramConfig, runtime: AgentRuntime) -> None:
        self.config = config
        self.runtime = runtime
        self._outgoing: asyncio.Queue[TelegramMessage] = asyncio.Queue(maxsize=100)
        self._tasks: list[asyncio.Task[None]] = []
        self._offset: int | None = None
        self._stopped = asyncio.Event()
        self._last_tool_notification_at = 0.0

    async def start(self) -> None:
        self._stopped.clear()
        self.runtime.events.subscribe(self.handle_event)
        self._tasks = [
            asyncio.create_task(self._outbound_loop(), name="telegram-outbound"),
            asyncio.create_task(self._poll_loop(), name="telegram-poll"),
        ]

    async def stop(self) -> None:
        self.runtime.events.unsubscribe(self.handle_event)
        self._stopped.set()
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def handle_event(self, event: AgentEvent) -> None:
        # Browser automation can issue many near-identical operations in a burst.
        # Keep the phone feed useful while failures and approvals remain unsuppressed.
        if event.type == "tool.started":
            now = time.monotonic()
            if now - self._last_tool_notification_at < 0.75:
                return
            self._last_tool_notification_at = now
        message = format_event(event)
        if message is None:
            return
        try:
            self._outgoing.put_nowait(message)
        except asyncio.QueueFull:
            logger.warning("Telegram notification queue is full; dropping a non-critical notification.")

    async def _outbound_loop(self) -> None:
        while not self._stopped.is_set():
            message = await self._outgoing.get()
            try:
                chunks = split_telegram_text(message.text)
                for index, chunk in enumerate(chunks):
                    payload: dict[str, Any] = {"chat_id": self.config.allowed_chat_id, "text": chunk}
                    if index == len(chunks) - 1 and message.keyboard:
                        payload["reply_markup"] = {"inline_keyboard": message.keyboard}
                    await self._call("sendMessage", payload)
            except Exception as exc:
                logger.warning("Telegram notification failed: %s", exc)
            finally:
                self._outgoing.task_done()

    async def _poll_loop(self) -> None:
        delay = 1
        while not self._stopped.is_set():
            try:
                payload: dict[str, Any] = {"timeout": 20, "allowed_updates": ["message", "callback_query"]}
                if self._offset is not None:
                    payload["offset"] = self._offset
                updates = await self._call("getUpdates", payload, timeout=25)
                for update in updates or []:
                    self._offset = max(self._offset or 0, int(update["update_id"]) + 1)
                    await self.handle_update(update)
                delay = 1
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Telegram polling failed: %s", exc)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)

    async def handle_update(self, update: dict[str, Any]) -> None:
        """Handle an update. Kept public to make authorization unit-testable."""
        callback = update.get("callback_query")
        message = update.get("message")
        source = callback.get("message", {}).get("chat", {}) if callback else (message or {}).get("chat", {})
        if source.get("id") != self.config.allowed_chat_id:
            logger.warning("Ignored Telegram control update from an unauthorized chat.")
            return
        if callback:
            await self._handle_callback(callback)
        elif message:
            text = str(message.get("text") or "").strip()
            if text:
                await self._handle_message(text)

    async def _handle_callback(self, callback: dict[str, Any]) -> None:
        callback_id = callback.get("id")
        data = str(callback.get("data") or "")
        if callback_id:
            await self._safe_answer_callback(callback_id)
        action, _, remainder = data.partition(":")
        if action in {"approve", "deny"}:
            resolved = self.runtime.approvals.resolve(remainder, action == "approve")
            await self._send_direct("Approval recorded." if resolved else "That approval request is no longer active.")
            return
        if action == "question":
            question_id, _, raw_index = remainder.partition(":")
            try:
                resolved = self.runtime.inputs.resolve_question_option(question_id, int(raw_index))
            except ValueError:
                resolved = False
            await self._send_direct("Answer recorded." if resolved else "That question is no longer active.")
            return
        if action == "command":
            await self._handle_message("/" + remainder)

    async def _handle_message(self, text: str) -> None:
        command = text.split(maxsplit=1)[0].lower()
        if command == "/status":
            await self._send_direct(self._status_text(), keyboard=[[{"text": "⏸ Pause", "callback_data": "command:pause"}, {"text": "🛑 Stop", "callback_data": "command:stop"}]])
            return
        if command == "/pause":
            changed = await self.runtime.controller.pause()
            await self._send_direct("⏸ Agent paused at the next safe boundary." if changed else "Agent is not currently running.")
            return
        if command == "/resume":
            changed = await self.runtime.controller.resume()
            await self._send_direct("▶️ Agent resumed." if changed else "Agent is not paused.")
            return
        if command == "/stop":
            changed = await self.runtime.controller.stop()
            await self._send_direct("🛑 Agent will stop after its current safe operation." if changed else "Agent is not currently running.")
            return
        if command == "/help":
            await self._send_direct("Commands:\n/status\n/pause\n/resume\n/stop\n/help\n\nOther messages are queued for the existing manager agent.")
            return
        await self.runtime.inputs.submit_message(text)

    def _status_text(self) -> str:
        snapshot = self.runtime.controller.snapshot()
        lines = [f"Agent: {snapshot.status.title()}"]
        if snapshot.current_task:
            lines.extend(["", f"Current task:\n{snapshot.current_task}"])
        if snapshot.current_operation:
            lines.extend(["", f"Current operation:\n{snapshot.current_operation}"])
        if snapshot.current_tool:
            lines.extend(["", f"Current tool:\n{snapshot.current_tool}"])
        if snapshot.progress_current is not None and snapshot.progress_total is not None:
            lines.extend(["", f"Progress:\n{snapshot.progress_current} / {snapshot.progress_total}"])
        if snapshot.started_at:
            runtime = datetime.now(timezone.utc) - snapshot.started_at
            lines.extend(["", f"Runtime:\n{str(runtime).split('.', 1)[0]}"])
        return "\n".join(lines)

    async def _send_direct(self, text: str, keyboard: list[list[dict[str, str]]] | None = None) -> None:
        for index, chunk in enumerate(split_telegram_text(text)):
            payload: dict[str, Any] = {"chat_id": self.config.allowed_chat_id, "text": chunk}
            if index == 0 and keyboard:
                payload["reply_markup"] = {"inline_keyboard": keyboard}
            try:
                await self._call("sendMessage", payload)
            except Exception as exc:
                logger.warning("Telegram command response failed: %s", exc)

    async def _safe_answer_callback(self, callback_id: str) -> None:
        try:
            await self._call("answerCallbackQuery", {"callback_query_id": callback_id})
        except Exception as exc:
            logger.warning("Telegram callback acknowledgement failed: %s", exc)

    async def _call(self, method: str, payload: dict[str, Any], timeout: int = 15) -> Any:
        return await asyncio.to_thread(self._request, method, payload, timeout)

    def _request(self, method: str, payload: dict[str, Any], timeout: int) -> Any:
        data = json.dumps(payload).encode("utf-8")
        request = Request(
            f"https://api.telegram.org/bot{self.config.token}/{method}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:  # nosec B310: fixed Telegram API host
                body = json.loads(response.read().decode("utf-8"))
        except URLError as exc:
            raise RuntimeError("Telegram API request failed") from exc
        if not body.get("ok"):
            raise RuntimeError("Telegram API returned an error")
        return body.get("result")
