"""Slash-command registry, pop-up autocomplete, styling, and handlers.

This module powers the interactive CLI experience:

1. Prefix Listener / Trigger Detector  -> the completer watches for a leading `/`
2. Command Registry & Fuzzy Matcher    -> COMMANDS + AgentCommandCompleter pop-up
3. ANSI / Syntax Tokenizer             -> Style applied to the prompt & menu
"""
from __future__ import annotations

import os
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from rich.console import Console

console = Console()

# --------------------------------------------------------------------------- #
# 1. & 2. Command Registry (registered skills / commands)
# --------------------------------------------------------------------------- #
COMMANDS: dict[str, str] = {
    "/index": "Scan repository and generate recursive explore.md site maps",
    "/help": "Show available agent commands and tool capabilities",
    "/clear": "Clear command and agent conversation history",
    "/plan": "Make the next request plan-only before execution",
}


# --------------------------------------------------------------------------- #
# 2. Pop-up Autocomplete Engine  (prefix listener + fuzzy matcher)
# --------------------------------------------------------------------------- #
class AgentCommandCompleter(Completer):
    """Renders a pop-up menu of registered commands once the user types `/`."""

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        # Trigger pop-up menu only when typing a slash command
        if text.startswith("/"):
            for cmd, description in COMMANDS.items():
                if cmd.startswith(text):
                    yield Completion(
                        cmd,
                        start_position=-len(text),
                        display=cmd,
                        display_meta=description,  # Right-aligned description
                    )


# --------------------------------------------------------------------------- #
# 3. UI Styling (ANSI / syntax tokenizer)
# --------------------------------------------------------------------------- #
COMMAND_STYLE = Style.from_dict(
    {
        # Pop-up menu colors
        "completion-menu.completion": "bg:#1e1e1e #888888",
        "completion-menu.completion.current": "bg:#005f87 #ffffff bold",
        "completion-menu.meta.completion": "bg:#1e1e1e #5f87af",
        "completion-menu.meta.completion.current": "bg:#005f87 #ffffff",
        # Prompt label color
        "prompt": "#00ffa3 bold",
        # Recognized slash command inside the prompt gets cyan/bold accent
        "slash-command": "#00ffff bold",
    }
)


def build_session(history):
    """Construct the PromptSession wired with autocomplete, style, and history."""
    return PromptSession(
        completer=AgentCommandCompleter(),
        style=COMMAND_STYLE,
        history=history,
    )


def prompt_for_input(session) -> str:
    """Render the styled prompt and return the raw user input."""
    return session.prompt(
        HTML("<prompt>Agent ❯ </prompt>")
    ).strip()


async def prompt_for_input_async(session) -> str:
    """Async counterpart used when the Telegram listener shares the event loop."""
    return (await session.prompt_async(HTML("<prompt>Agent ❯ </prompt>"))).strip()


# --------------------------------------------------------------------------- #
# Command handlers
# --------------------------------------------------------------------------- #
IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
    "dist",
    "build",
    ".ruff_cache",
    ".tox",
}
IGNORED_FILES = {".DS_Store", "explore.md"}


def _build_tree(root: Path, prefix: str = "") -> list[str]:
    """Recursively build a markdown tree of the repository."""
    lines: list[str] = []
    try:
        entries = sorted(
            root.iterdir(),
            key=lambda p: (p.is_file(), p.name.lower()),
        )
    except (PermissionError, OSError):
        return lines

    dirs = [e for e in entries if e.is_dir() and e.name not in IGNORED_DIRS]
    files = [e for e in entries if e.is_file() and e.name not in IGNORED_FILES]

    for i, entry in enumerate(dirs + files):
        last = i == len(dirs) + len(files) - 1
        branch = "└── " if last else "├── "
        lines.append(f"{prefix}{branch}{entry.name}")

        if entry.is_dir():
            lines.extend(_build_tree(entry, prefix + ("    " if last else "│   ")))

    return lines


def run_index() -> None:
    """Scan the repository and generate a recursive explore.md site map."""
    root = Path.cwd()
    console.print("\n[cyan][Skill Triggered][/cyan] Executing Codebase Indexing Pipeline...")

    tree_lines = _build_tree(root)
    if not tree_lines:
        console.print("[yellow]No indexable files found.[/yellow]\n")
        return

    lines = [
        "# explore.md — Codebase Site Map",
        "",
        f"Generated for `{root.name}` at `{Path.cwd()}`",
        "",
        "```",
        f"{root.name}/",
        *tree_lines,
        "```",
        "",
    ]

    target = root / "explore.md"
    target.write_text("\n".join(lines), encoding="utf-8")
    console.print(
        f"[green]✓ Codebase indexed! {len(tree_lines)} entries written to "
        f"[bold]{target}[/bold].[/green]\n"
    )


def run_help() -> None:
    """Show available commands and tool capabilities."""
    console.print("\n[bold yellow]Available agent commands:[/bold yellow]")
    for cmd, description in COMMANDS.items():
        console.print(f"  [cyan bold]{cmd:<8}[/cyan bold] {description}")
    console.print(
        "\n[bold yellow]Tool capabilities:[/bold yellow]\n"
        "  terminal    Execute a terminal command and return its output\n"
        "  web_search  Search the web for data\n"
        "  read_file   Read the contents of a file\n"
        "  update_file Edit the content of a file by replacing a substring\n"
        "\n[dim]Use a command by entering it exactly on its own line. "
        "Type [bold]/[/bold] to open the autocomplete pop-up.[/dim]\n"
    )


def run_clear() -> None:
    """Clear the conversation history (handled by the caller for state reset)."""
    console.print("\n[yellow]Conversation history cleared. Working state reset.[/yellow]\n")


def run_plan() -> None:
    """Enable plan-only mode for the next natural-language request."""
    console.print(
        "\n[magenta][Plan Mode][/magenta] Your next request will receive a "
        "step-by-step plan without tool execution.\n"
    )


# --------------------------------------------------------------------------- #
# Dispatcher
# --------------------------------------------------------------------------- #
_HANDLERS = {
    "/index": run_index,
    "/help": run_help,
    "/clear": run_clear,
    "/plan": run_plan,
}


def is_command(text: str) -> bool:
    """Return True if `text` is a registered slash command."""
    return text in COMMANDS


def dispatch(command: str):
    """Run the handler for a registered slash command."""
    handler = _HANDLERS.get(command)
    if handler is None:
        console.print(f"[bold red]Unknown command:[/bold red] {command}\n")
        return
    handler()


def reset_history(history) -> None:
    """Empty the given prompt_toolkit history."""
    # prompt_toolkit's InMemoryHistory does not expose pop() or clear().
    # Clear both backing collections so entries do not reappear on the next
    # prompt after the history loader has already run.
    if hasattr(history, "_storage"):
        history._storage.clear()
    if hasattr(history, "_loaded_strings"):
        history._loaded_strings.clear()
