import os
import re
import hashlib
import json
from datetime import datetime, timezone
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
PENDING_QUESTIONS_FILE_PATH = QNA_FILE_PATH.with_name("pending_questions.json")


def _normalize_question(question: str) -> str:
    """Return a stable key used to prevent duplicate unanswered questions."""
    return re.sub(r"\s+", " ", question.strip()).casefold()


def record_pending_question(question: str, placeholder_answer: str) -> dict:
    """Create or update one reviewable pending-question record.

    Pending records are intentionally separate from confirmed profile answers.
    Repeated sightings increment ``seen_count`` instead of duplicating the
    question, and any distinct fallbacks are retained for the user's review.
    """
    clean_question = question.strip()
    clean_answer = placeholder_answer.strip()
    if not clean_question:
        raise ValueError("Question must not be empty.")
    if not clean_answer:
        raise ValueError("Placeholder answer must not be empty.")

    PENDING_QUESTIONS_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if PENDING_QUESTIONS_FILE_PATH.exists():
        try:
            data = json.loads(PENDING_QUESTIONS_FILE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{PENDING_QUESTIONS_FILE_PATH.name} is not valid JSON; repair it before recording more questions."
            ) from exc
    else:
        data = {"version": 1, "questions": []}

    questions = data.get("questions")
    if not isinstance(questions, list):
        raise ValueError(f"{PENDING_QUESTIONS_FILE_PATH.name} must contain a 'questions' list.")

    normalized_question = _normalize_question(clean_question)
    now = datetime.now(timezone.utc).isoformat()
    for entry in questions:
        if entry.get("normalized_question") != normalized_question:
            continue
        answers_seen = entry.setdefault("placeholder_answers_seen", [])
        if clean_answer not in answers_seen:
            answers_seen.append(clean_answer)
        entry["last_seen_at"] = now
        entry["seen_count"] = int(entry.get("seen_count", 0)) + 1
        _write_pending_questions(data)
        return {"created": False, "id": entry["id"], "seen_count": entry["seen_count"]}

    entry = {
        "id": hashlib.sha256(normalized_question.encode("utf-8")).hexdigest()[:16],
        "question": clean_question,
        "normalized_question": normalized_question,
        "status": "pending",
        "placeholder_answers_seen": [clean_answer],
        "first_seen_at": now,
        "last_seen_at": now,
        "seen_count": 1,
    }
    questions.append(entry)
    _write_pending_questions(data)
    return {"created": True, "id": entry["id"], "seen_count": 1}


def _write_pending_questions(data: dict) -> None:
    """Atomically replace the pending queue after a successful JSON update."""
    temporary_path = PENDING_QUESTIONS_FILE_PATH.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary_path.replace(PENDING_QUESTIONS_FILE_PATH)


def record_placeholder_question(question: str, placeholder_answer: str) -> bool:
    """Append one canonical unanswered-Q&A block unless that question is present.

    This deliberately owns the append operation.  Letting an LLM use a generic
    string-replace tool for appends is unsafe: ``str.replace('', value)`` inserts
    ``value`` between every character in the file.

    Returns ``True`` when a new entry was added and ``False`` for a duplicate.
    """
    clean_question = question.strip()
    clean_answer = placeholder_answer.strip()
    if not clean_question:
        raise ValueError("Question must not be empty.")
    if not clean_answer:
        raise ValueError("Placeholder answer must not be empty.")

    QNA_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    content = QNA_FILE_PATH.read_text(encoding="utf-8") if QNA_FILE_PATH.exists() else ""
    requested_key = _normalize_question(clean_question)
    recorded_questions = re.findall(r"(?m)^\s*-\s*Question:\s*(.+?)\s*$", content)

    if any(_normalize_question(item) == requested_key for item in recorded_questions):
        return False

    entry = (
        ("\n" if content.strip() else "")
        + "# NEEDS ANSWER\n"
        f"- Question: {clean_question}\n"
        f"- Placeholder answer used: {clean_answer}\n"
    )
    QNA_FILE_PATH.write_text(content.rstrip() + entry, encoding="utf-8")
    return True


def build_qna_context(max_entries: int = 100, max_characters: int = 8_000) -> str:
    """Return answered Q&A entries suitable for a worker prompt.

    Unanswered ``# NEEDS ANSWER`` blocks are intentionally excluded: their
    placeholders are application fallbacks, not user-confirmed facts.  The
    result is bounded so a damaged or unusually large qna.md cannot consume a
    worker's context window.
    """
    if not QNA_FILE_PATH.exists():
        return "No answered Q&A entries are recorded."

    entries: list[str] = []
    seen_questions: set[str] = set()
    for line in QNA_FILE_PATH.read_text(encoding="utf-8").splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith(("#", "-")):
            continue
        match = re.match(r"^(.+?)\s+(?:=|—)\s+(.+?)$", candidate)
        if not match:
            continue
        question, answer = (part.strip() for part in match.groups())
        question_key = _normalize_question(question)
        if not question_key or question_key in seen_questions:
            continue
        seen_questions.add(question_key)
        entries.append(f"- {question}: {answer}")
        if len(entries) >= max_entries or sum(map(len, entries)) >= max_characters:
            break

    return "\n".join(entries) if entries else "No answered Q&A entries are recorded."


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
