"""Non-sensitive, atomic checkpoints for resumable job applications."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.logging import redact_sensitive

CHECKPOINT_DIR = Path(os.getenv("APPLICATION_CHECKPOINT_DIR", "data/application_checkpoints"))
_ALLOWED = {
    "job_id", "ats", "url", "step", "step_name", "account_verified",
    "resume_uploaded", "completed_fields", "pending_fields", "failure_code",
    "failure_detail", "last_completed_step", "retryable", "last_attempted_at",
    "captcha_status", "captcha_detected_at", "captcha_completed_at",
    "captcha_url", "queue_ready_at",
}
_SENSITIVE_FRAGMENTS = ("password", "cookie", "token", "secret", "authorization", "otp", "demographic")


def sanitize_checkpoint(data: dict[str, Any]) -> dict[str, Any]:
    safe = {}
    for key, value in data.items():
        lowered = str(key).lower()
        if key in _ALLOWED and not any(fragment in lowered for fragment in _SENSITIVE_FRAGMENTS):
            safe[key] = redact_sensitive(value)
    safe["job_id"] = str(safe.get("job_id", "Unknown"))
    safe["updated_at"] = datetime.now(timezone.utc).isoformat()
    return safe


class ApplicationCheckpointStore:
    def __init__(self, directory: Path | None = None):
        self.directory = Path(directory or CHECKPOINT_DIR)

    def path_for(self, job_id: str) -> Path:
        safe_id = "".join(ch for ch in str(job_id) if ch.isalnum() or ch in "-_") or "Unknown"
        return self.directory / f"{safe_id}.json"

    def save(self, checkpoint: dict[str, Any]) -> dict[str, Any]:
        safe = sanitize_checkpoint(checkpoint)
        path = self.path_for(safe["job_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(safe, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(path)
        return safe

    def load(self, job_id: str) -> dict[str, Any] | None:
        path = self.path_for(job_id)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def record_step(self, job_id: str, **updates: Any) -> dict[str, Any]:
        current = self.load(job_id) or {"job_id": str(job_id)}
        # Failure handlers often know less than the last successful browser
        # action.  Never let an absent value erase resumable progress.
        current.update({key: value for key, value in updates.items() if value is not None})
        current["last_attempted_at"] = datetime.now(timezone.utc).isoformat()
        return self.save(current)
