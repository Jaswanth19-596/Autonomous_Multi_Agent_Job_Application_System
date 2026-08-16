"""Presentation-only formatting for Telegram notifications."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.notifications.events import AgentEvent
from src.core.logging import redact_sensitive

MAX_TELEGRAM_MESSAGE = 4000


@dataclass(frozen=True, slots=True)
class TelegramMessage:
    text: str
    keyboard: list[list[dict[str, str]]] | None = None


def split_telegram_text(text: str, limit: int = MAX_TELEGRAM_MESSAGE) -> list[str]:
    """Return safe Telegram-sized chunks, preserving useful boundaries where possible."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


def _brief(value: Any, limit: int = 1200) -> str:
    rendered = str(redact_sensitive(value))
    if len(rendered) <= limit:
        return rendered
    return f"{rendered[:limit]}\n\n[Output truncated: {len(rendered):,} characters]"


def _tool_event(event: AgentEvent, title: str) -> TelegramMessage:
    data = event.data
    text = f"{title}\n{data.get('tool', 'unknown_tool')}"
    if data.get("args"):
        text += f"\n\nArguments:\n{_brief(data['args'], 1000)}"
    if data.get("result"):
        text += f"\n\nOutput:\n{_brief(data['result'])}"
    if data.get("error"):
        text += f"\n\nError:\n{_brief(data['error'])}"
    return TelegramMessage(text)


def format_event(event: AgentEvent) -> TelegramMessage | None:
    """Filter routine events and format the useful ones for a phone-sized screen."""
    data = event.data
    if event.type == "agent.started":
        task = data.get("task")
        return TelegramMessage("🤖 Agent Started" + (f"\n\nTask:\n{task}" if task else ""))
    if event.type == "agent.completed":
        return TelegramMessage("🏁 Agent Completed")
    if event.type == "task.started":
        return TelegramMessage(f"📋 Task Started\n\n{_brief(data.get('task', ''), 2000)}")
    if event.type == "agent.message":
        content = data.get("content")
        return TelegramMessage(f"🤖 Agent\n\n{_brief(content, 2500)}") if content else None
    if event.type == "tool.started":
        return _tool_event(event, "🔧 Tool Started")
    if event.type == "tool.completed":
        return _tool_event(event, "✅ Tool Completed") if data.get("notify_completion") else None
    if event.type == "tool.failed":
        return _tool_event(event, "❌ Tool Failed")
    if event.type == "job.started":
        return TelegramMessage(
            "💼 Job Started\n\n"
            f"Company: {data.get('company', 'Unknown')}\n"
            f"Role: {data.get('title', 'Unknown')}"
        )
    if event.type == "job.completed":
        return TelegramMessage(
            "✅ Job Completed\n\n"
            f"Company: {data.get('company', 'Unknown')}\n"
            f"Role: {data.get('title', 'Unknown')}"
        )
    if event.type == "job.failed":
        return TelegramMessage(
            "❌ Job Failed\n\n"
            f"Company: {data.get('company', 'Unknown')}\n"
            f"Role: {data.get('title', 'Unknown')}\n\n"
            f"Error:\n{_brief(data.get('error', 'Unknown error'))}"
        )
    if event.type == "agent.question":
        keyboard = [[{"text": option, "callback_data": f"question:{data['question_id']}:{index}"}]
                    for index, option in enumerate(data.get("options", []))]
        text = f"❓ Agent Question\n\n{data.get('question', '')}"
        return TelegramMessage(text, keyboard or None)
    if event.type == "approval.required":
        calls = data.get("tool_calls", [])
        details = "\n\n".join(
            f"Tool:\n{call.get('name', 'unknown')}\n\nArguments:\n{_brief(call.get('args', {}), 1000)}"
            for call in calls
        )
        approval_id = data["approval_id"]
        return TelegramMessage(
            f"⚠️ APPROVAL REQUIRED\n\n{details}",
            [[
                {"text": "✅ Approve", "callback_data": f"approve:{approval_id}"},
                {"text": "❌ Deny", "callback_data": f"deny:{approval_id}"},
            ]],
        )
    if event.type == "system.error":
        return TelegramMessage(f"🚨 System Error\n\n{_brief(data.get('error', 'Unknown error'))}")
    return None
