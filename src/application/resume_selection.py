"""Per-application selection and enforcement of the resume being uploaded."""

from __future__ import annotations

import contextvars
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BASE_RESUME = ROOT / "user_details" / "resume.pdf"
_active_tailored_resume: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "active_tailored_resume", default=None
)


def clear_active_tailored_resume() -> None:
    """Clear selection before starting a different job application."""
    _active_tailored_resume.set(None)


def activate_tailored_resume(path: Path | str) -> Path:
    """Make an existing tailored PDF mandatory for the current application."""
    candidate = Path(path).expanduser().resolve()
    if candidate.suffix.lower() != ".pdf" or not candidate.is_file():
        raise ValueError(f"Tailored resume PDF does not exist: {candidate}")
    _active_tailored_resume.set(candidate)
    return candidate


def active_tailored_resume() -> Path | None:
    """Return the tailored PDF selected for this application, if any."""
    return _active_tailored_resume.get()


def tailored_resume_requirement() -> str | None:
    """Give browser-driving tools an unambiguous document invariant."""
    path = active_tailored_resume()
    if path is None:
        return None
    return (
        "TAILORED_RESUME_REQUIRED: Simplify may have attached its saved resume. "
        f"Before continuing, manually upload and verify this exact tailored PDF: {path}. "
        "Do not submit while a differently named resume is selected."
    )


def enforce_tailored_resume_paths(value: Any) -> Any:
    """Replace normal-resume path references in browser tool arguments.

    This covers the normal file-upload tool as well as the occasional
    ``browser_run_code_unsafe`` upload snippet.  Cover-letter paths are left
    unchanged, and already-tailored resume paths are never modified.
    """
    tailored = active_tailored_resume()
    if tailored is None:
        return value

    replacements = {
        str(BASE_RESUME): str(tailored),
        "user_details/resume.pdf": str(tailored),
    }

    if isinstance(value, str):
        updated = value
        for source, replacement in replacements.items():
            updated = updated.replace(source, replacement)
        return updated
    if isinstance(value, dict):
        return {key: enforce_tailored_resume_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [enforce_tailored_resume_paths(item) for item in value]
    if isinstance(value, tuple):
        return tuple(enforce_tailored_resume_paths(item) for item in value)
    return value


def build_tailored_resume_replacement_code(path: Path | str | None = None) -> str:
    """Build Playwright code that replaces a Simplify-attached resume in place."""
    tailored = Path(path or active_tailored_resume() or "").expanduser().resolve()
    if not tailored.is_file():
        raise ValueError("An active tailored resume PDF is required for replacement.")
    file_path = json.dumps(str(tailored))
    file_name = json.dumps(tailored.name)
    return f"""
async (page) => {{
  const filePath = {file_path};
  const fileName = {file_name};
  const inputs = page.locator('input[type=file]');
  const candidates = [];
  for (let index = 0; index < await inputs.count(); index++) {{
    const input = inputs.nth(index);
    const identity = [
      await input.getAttribute('name'), await input.getAttribute('id'),
      await input.getAttribute('aria-label'), await input.getAttribute('accept')
    ].filter(Boolean).join(' ').toLowerCase();
    if ((await inputs.count()) === 1 || /resume|curriculum|\\bcv\\b/.test(identity)) {{
      candidates.push(input);
    }}
  }}
  if (candidates.length !== 1) {{
    return JSON.stringify({{replaced:false, reason:candidates.length ? 'ambiguous_file_inputs' : 'resume_file_input_not_found'}});
  }}
  const target = candidates[0];
  await target.setInputFiles(filePath);
  await page.waitForTimeout(400);
  const files = await target.evaluate(input => Array.from(input.files || []).map(file => file.name));
  return JSON.stringify({{replaced:files.includes(fileName), files}});
}}
"""
