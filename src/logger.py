import contextvars
from pathlib import Path
from datetime import datetime
from rich.console import Console

console = Console()

current_job_id_var = contextvars.ContextVar("current_job_id", default=None)
current_company_var = contextvars.ContextVar("current_company", default=None)
current_log_file_var = contextvars.ContextVar("current_log_file", default=None)

LOGS_DIR = Path("logs/jobs")


def setup_job_logger(job_id: str, company: str, title: str) -> Path:
    """Set context variables for the current async task and create a dedicated log file."""
    current_job_id_var.set(str(job_id))
    current_company_var.set(str(company))

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    sanitized_company = "".join(c for c in str(company) if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")
    log_file = LOGS_DIR / f"{job_id}_{sanitized_company}.log"
    current_log_file_var.set(log_file)

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"=== Job Application Log: {job_id} | {title} at {company} [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ===\n\n")

    return log_file


def log_event(event_type: str, details: str):
    """Log an event to the current job's dedicated log file."""
    log_file = current_log_file_var.get()
    if log_file:
        timestamp = datetime.now().strftime("%H:%M:%S")
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] [{event_type}] {details}\n")
        except Exception:
            pass


def get_job_prefix() -> str:
    """Get the formatted prefix for standard output (e.g. '[Job 4451196390 | ATC]')."""
    job_id = current_job_id_var.get()
    company = current_company_var.get()
    if job_id and company:
        return f"[bold magenta][Job {job_id} | {company}][/bold magenta] "
    elif job_id:
        return f"[bold magenta][Job {job_id}][/bold magenta] "
    return ""
