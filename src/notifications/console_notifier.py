"""Rich terminal projection for the same structured events sent to Telegram."""
from __future__ import annotations

from rich.console import Console

from src.core.logging import redact_sensitive
from src.notifications.events import AgentEvent


class RichConsoleNotifier:
    """Keep existing terminal observability while avoiding Telegram coupling in nodes."""

    def __init__(self, console: Console) -> None:
        self.console = console

    async def __call__(self, event: AgentEvent) -> None:
        if event.type == "tool.started":
            self.console.print(
                f"\n{event.data.get('prefix', '')}[bold yellow]🛠️  Executing Tool:[/bold yellow] "
                f"[bold cyan]{event.data.get('tool', 'unknown')}[/bold cyan]"
            )
            if event.data.get("args"):
                self.console.print(f"[dim]   Args:[/dim] {redact_sensitive(event.data['args'])}")
        elif event.type == "tool.failed":
            self.console.print(
                f"{event.data.get('prefix', '')}[red]Tool '{event.data.get('tool', 'unknown')}' failed: "
                f"{event.data.get('error', 'Unknown error')}[/red]"
            )
        elif event.type == "system.error":
            self.console.print(f"[bold red]System error: {event.data.get('error', 'Unknown error')}[/bold red]")
