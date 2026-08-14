import os
import re
from pathlib import Path
from typing import Any, List, Union

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style
from prompt_toolkit.shortcuts import prompt
from rich.console import Console

console = Console()
QNA_FILE_PATH = Path(__file__).resolve().parents[2] / "user_details" / "qna.md"


def update_qna_file(question: str, answer: str) -> None:
    """
    Updates or appends a question-answer pair in user_details/qna.md.
    If an existing key or placeholder match is found, it updates it. Otherwise, it appends.
    """
    if not QNA_FILE_PATH.exists():
        QNA_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        lines = []
    else:
        with open(QNA_FILE_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

    clean_question = question.strip()
    clean_answer = answer.strip()

    # Try finding existing matching question line (case-insensitive substring or key match)
    updated = False
    new_lines = []

    for line in lines:
        stripped = line.strip()
        # Check if line matches question key before '=' or '—' or ':'
        if not updated and stripped:
            norm_line = stripped.lower()
            norm_q = clean_question.lower()

            # Direct key match or '# NEEDS ANSWER' placeholder replacement
            if norm_q in norm_line or norm_line.startswith(norm_q):
                new_lines.append(f"{clean_question} — {clean_answer}\n")
                updated = True
                continue

        new_lines.append(line)

    if not updated:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f"{clean_question} = {clean_answer}\n")

    with open(QNA_FILE_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    console.print(f"[bold green]✓ Updated {QNA_FILE_PATH.name} with answer:[/bold green] [cyan]{clean_answer}[/cyan]\n")


def interactive_ask_user(
    question: str,
    options: Union[List[Union[str, dict]], None] = None,
    multi_select: bool = False,
    allow_custom: bool = True,
) -> str:
    """
    Displays an interactive Claude Code style selection menu in the CLI.
    """
    if options is None:
        options = ["Yes", "No"]

    # Normalize options to dicts with label and description
    norm_options: List[dict] = []
    for opt in options:
        if isinstance(opt, str):
            norm_options.append({"label": opt, "description": ""})
        elif isinstance(opt, dict):
            label = opt.get("label") or opt.get("title") or opt.get("text") or str(opt)
            desc = opt.get("description") or opt.get("details") or opt.get("subtext") or ""
            norm_options.append({"label": label, "description": desc})

    if allow_custom and not any(o["label"] == "Type something" for o in norm_options):
        norm_options.append({"label": "Type something", "description": "Enter a custom text response"})

    current_index = 0
    selected_indices = set()
    result = {"answer": None, "custom": False}

    kb = KeyBindings()

    @kb.add("up")
    @kb.add("k")
    def _go_up(event):
        nonlocal current_index
        if current_index > 0:
            current_index -= 1
        else:
            current_index = len(norm_options) - 1

    @kb.add("down")
    @kb.add("j")
    @kb.add("tab")
    def _go_down(event):
        nonlocal current_index
        if current_index < len(norm_options) - 1:
            current_index += 1
        else:
            current_index = 0

    @kb.add("space")
    def _toggle_space(event):
        nonlocal current_index
        if multi_select:
            if current_index in selected_indices:
                selected_indices.remove(current_index)
            else:
                selected_indices.add(current_index)

    @kb.add("enter")
    def _select_enter(event):
        nonlocal current_index
        chosen = norm_options[current_index]
        if chosen["label"] == "Type something":
            result["custom"] = True
            event.app.exit(result=None)
        else:
            if multi_select and selected_indices:
                answers = [norm_options[i]["label"] for i in sorted(selected_indices)]
                result["answer"] = ", ".join(answers)
            else:
                result["answer"] = chosen["label"]
            event.app.exit(result=result["answer"])

    @kb.add("c-c")
    @kb.add("escape")
    def _cancel(event):
        event.app.exit(result=None)

    def get_formatted_text():
        fragments = []
        # Header banner (Claude Code / IDE tabs look)
        fragments.append(("class:header-tab", " Storage "))
        fragments.append(("", " "))
        fragments.append(("class:header-tab", " Erreurs LLM "))
        fragments.append(("", " "))
        fragments.append(("class:header-tab-active", " Scope "))
        fragments.append(("", " "))
        fragments.append(("class:header-tab", " UI "))
        fragments.append(("", " "))
        fragments.append(("class:header-submit", " ✓ Submit → "))
        fragments.append(("", "\n\n"))

        # Question prompt
        fragments.append(("class:question", f"{question}\n\n"))

        # Options list
        for idx, item in enumerate(norm_options):
            is_hovered = (idx == current_index)
            is_checked = (idx in selected_indices) if multi_select else is_hovered

            cursor = "❯ " if is_hovered else "  "
            chk = "[✓]" if is_checked else "[ ]"
            num = f"{idx + 1}. "

            cursor_style = "class:cursor" if is_hovered else ""
            num_style = "class:num" if is_hovered else "class:dim"
            chk_style = "class:checked" if is_checked else "class:unchecked"
            label_style = "class:label-hover" if is_hovered else "class:label"

            fragments.append((cursor_style, cursor))
            fragments.append((num_style, num))
            fragments.append((chk_style, f"{chk} "))
            fragments.append((label_style, f"{item['label']}\n"))

            if item["description"]:
                fragments.append(("class:description", f"     {item['description']}\n"))

        fragments.append(("", "\n"))
        fragments.append(("class:footer", "Enter to select · Tab/Arrow keys to navigate · Esc to cancel"))
        return fragments

    style = Style.from_dict({
        "header-tab": "bg:#2b2b36 #8888aa",
        "header-tab-active": "bg:#5b5bd6 #ffffff bold",
        "header-submit": "#00ffaa bold",
        "question": "#ffffff bold",
        "cursor": "#5b5bd6 bold",
        "num": "#aaaabb",
        "checked": "#00ffaa bold",
        "unchecked": "#666688",
        "label-hover": "#5b5bd6 bold underline",
        "label": "#dddddd",
        "description": "#9999aa italic",
        "footer": "#777788",
        "dim": "#555566",
    })

    control = FormattedTextControl(get_formatted_text)
    window = Window(content=control)
    layout = Layout(HSplit([window]))
    app = Application(layout=layout, key_bindings=kb, style=style, full_screen=False)

    ans = app.run()

    if result.get("custom"):
        console.print("\n[bold cyan]Type your response:[/bold cyan]")
        custom_val = prompt("❯ ").strip()
        return custom_val

    return ans or "No response provided"


def interactive_collect_fields(title: str, fields: list[dict], repeat: int = 1) -> dict:
    """Collect typed structured data without degrading free text to Yes/No."""
    console.print(f"\n[bold cyan]{title}[/bold cyan]")
    collected: dict[str, Any] = {}
    for index in range(max(1, repeat)):
        row: dict[str, str] = {}
        if repeat > 1:
            console.print(f"[dim]Entry {index + 1} of {repeat}[/dim]")
        for spec in fields:
            key = str(spec.get("key") or spec.get("label") or "value")
            label = str(spec.get("label") or key.replace("_", " ").title())
            required = bool(spec.get("required", False))
            while True:
                value = prompt(f"{label}: ").strip()
                if value or not required:
                    break
                console.print("[yellow]This value is required.[/yellow]")
            row[key] = value
        if repeat == 1:
            collected.update(row)
        else:
            collected[str(index + 1)] = row
    return collected
