"""Per-job application runtime and tool-call metrics."""

from __future__ import annotations

import contextvars
import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse

from src.data.jobs_workbook import update_job_row


JOBS_FILE = Path(__file__).resolve().parents[2] / "data" / "jobs.xlsx"
OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"
_WRITE_LOCK = threading.Lock()


@dataclass
class ApplicationMetricSession:
    job_id: str
    jobboard: str
    source_url: str | None
    model: str | None
    started_at: datetime
    started_monotonic: float
    openrouter_usage_before_usd: float | None = None
    openrouter_credits_before_usd: float | None = None
    tool_calls: int = 0


_current_session: contextvars.ContextVar[ApplicationMetricSession | None] = (
    contextvars.ContextVar("application_metric_session", default=None)
)


def identify_jobboard(url: str | None) -> str:
    """Return a stable job-board label derived from an application URL."""
    hostname = (urlparse(url or "").hostname or "").lower()
    hostname = hostname.removeprefix("www.")
    known_boards = {
        "myworkdayjobs.com": "workday",
        "workday.com": "workday",
        "greenhouse.io": "greenhouse",
        "lever.co": "lever",
        "ashbyhq.com": "ashby",
        "icims.com": "icims",
        "jobvite.com": "jobvite",
        "bamboohr.com": "bamboohr",
        "paylocity.com": "paylocity",
        "ultipro.com": "ultipro",
        "ukg.com": "ultipro",
        "silkroad.com": "silkroad",
        "rippling.com": "rippling",
        "successfactors.com": "successfactors",
        "deloitte.com": "deloitte",
        "horizontaltalent.com": "horizontaltalent",
        "linkedin.com": "linkedin",
    }
    for domain, label in known_boards.items():
        if hostname == domain or hostname.endswith(f".{domain}"):
            return label
    return hostname or "unknown"


def fetch_openrouter_credit_snapshot(api_key: str | None = None) -> dict:
    """Fetch cumulative usage and remaining key credits from OpenRouter."""
    key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return {"usage_usd": None, "credits_remaining_usd": None}
    request = Request(
        OPENROUTER_KEY_URL,
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.load(response).get("data", {})
        usage = payload.get("usage")
        remaining = payload.get("limit_remaining")
        return {
            "usage_usd": float(usage) if usage is not None else None,
            "credits_remaining_usd": float(remaining) if remaining is not None else None,
        }
    except Exception:
        # Metrics must never interrupt an application attempt.
        return {"usage_usd": None, "credits_remaining_usd": None}


def start_application_metrics(
    job_id: str,
    apply_url: str | None,
    credit_snapshot: dict | None = None,
    model: str | None = None,
) -> None:
    """Start tracking metrics in the current async execution context."""
    snapshot = credit_snapshot or {}
    source_board = identify_jobboard(apply_url)
    _current_session.set(
        ApplicationMetricSession(
            job_id=str(job_id),
            # LinkedIn is a source, not the application platform. Leave this
            # unknown until the worker reaches its redirected ATS page.
            jobboard="unknown" if source_board == "linkedin" else source_board,
            source_url=apply_url,
            model=model,
            started_at=datetime.now(timezone.utc),
            started_monotonic=time.monotonic(),
            openrouter_usage_before_usd=snapshot.get("usage_usd"),
            openrouter_credits_before_usd=snapshot.get("credits_remaining_usd"),
        )
    )


def record_tool_call() -> None:
    """Count one worker tool invocation, if an application is active."""
    session = _current_session.get()
    if session is not None:
        session.tool_calls += 1


def record_application_destination(url: str | None) -> None:
    """Prefer the redirected ATS URL over the LinkedIn source URL."""
    session = _current_session.get()
    if session is None or not url:
        return
    board = identify_jobboard(url)
    if board != "linkedin":
        session.jobboard = board
        session.source_url = url


def finish_application_metrics(
    status: str,
    *,
    company: str = "",
    title: str = "",
    credit_snapshot: dict | None = None,
    application_url: str | None = None,
    workbook_path: Path | None = None,
) -> dict | None:
    """Finalize the active session and update its row in jobs.xlsx."""
    session = _current_session.get()
    if session is None:
        return None

    record_application_destination(application_url)

    finished_at = datetime.now(timezone.utc)
    snapshot = credit_snapshot or {}
    usage_after = snapshot.get("usage_usd")
    cost = None
    if session.openrouter_usage_before_usd is not None and usage_after is not None:
        cost = max(0.0, usage_after - session.openrouter_usage_before_usd)

    metrics = {
        "jobboard": session.jobboard,
        "model": session.model,
        "application_url": session.source_url,
        "application_started_at": session.started_at.replace(tzinfo=None),
        "application_finished_at": finished_at.replace(tzinfo=None),
        "application_duration_seconds": round(
            time.monotonic() - session.started_monotonic, 3
        ),
        "application_tool_calls": session.tool_calls,
        "application_cost_usd": round(cost, 8) if cost is not None else None,
        "openrouter_credits_before_usd": session.openrouter_credits_before_usd,
        "openrouter_credits_after_usd": snapshot.get("credits_remaining_usd"),
        "application_metrics_status": status,
    }
    destination = workbook_path or JOBS_FILE
    with _WRITE_LOCK:
        if not destination.exists():
            raise FileNotFoundError(f"Jobs workbook not found: {destination}")
        update_job_row(destination, session.job_id, metrics)

    _current_session.set(None)
    return {"job_id": session.job_id, "company": company, "title": title, **metrics}
