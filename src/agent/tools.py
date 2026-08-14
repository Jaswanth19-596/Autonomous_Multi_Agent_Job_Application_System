import os
import asyncio
import json
import re
import warnings
from pathlib import Path
from dotenv import load_dotenv

from langchain_community.tools import ShellTool
from langchain_core.tools import tool
from langchain_tavily import TavilySearch
from rich.console import Console
from langchain_core.messages import SystemMessage, HumanMessage
from pypdf import PdfReader

warnings.filterwarnings("ignore", category=UserWarning, module="langchain_community.tools.shell.tool")
warnings.filterwarnings("ignore", message=".*shell tool has no safeguards.*")

load_dotenv()


console = Console()

tools_by_name = {}
worker_model_holder = {"model": None}


from rich.panel import Panel
from src.cli.ui_qna import (
    PENDING_QUESTIONS_FILE_PATH,
    QNA_FILE_PATH,
    build_qna_context,
    interactive_ask_user,
    record_pending_question,
    update_qna_file,
)
from src.data.user_profile import UserProfile

import pandas as pd
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parents[2]
_EXCEL_PATH = _BASE_DIR / "data" / "jobs.xlsx"
_JOBBOARD_SKILLS_DIR = _BASE_DIR / "skills" / "jobboards"


@tool
def ask_user(question: str, options: list = None, multi_select: bool = False) -> str:
    """Ask the user a question interactively with selectable options during execution.
    The user's response is automatically saved to user_details/qna.md for future reference.

    Args:
        question: The question prompt to present to the user.
        options: Optional list of choices for the user. Options can be strings or dicts with 'label' and 'description'.
        multi_select: Whether the user can select multiple options.
    """
    answer = interactive_ask_user(question=question, options=options, multi_select=multi_select)
    update_qna_file(question=question, answer=answer)
    return f"User selected answer: '{answer}'"


@tool
def record_pending_application_question(question: str, placeholder_answer: str) -> str:
    """Record an unknown application question in pending_questions.json.

    Use this after selecting a reasonable fallback. The user reviews this queue
    and manually promotes confirmed answers into their profile. Do not use
    read_file or update_file for pending_questions.json.
    """
    result = record_pending_question(question, placeholder_answer)
    if result["created"]:
        return f"Recorded pending question {result['id']} in pending_questions.json."
    return (
        f"Updated existing pending question {result['id']} "
        f"(seen {result['seen_count']} times); no duplicate was added."
    )


@tool
async def delegate_job_application(job_details: dict) -> dict:
    """Delegate a single job application to a worker subagent.
    The worker gets exclusive access to the browser. Jobs are processed one at a time.

    Args:
        job_details: Dict containing the full job record from get_jobs (must include 'id', 'title', 'companyName', and 'link' or 'applyUrl').
    """
    from src.agent.app import MODEL_NAME, build_worker_graph, WORKER_SYSTEM_PROMPT
    # pyrefly: ignore [missing-import]
    from src.automation.simplify_auto import reset_auto_simplify_attempts

    user_profile = UserProfile.build_user_profile(
    str(_BASE_DIR / "data" / "user_profile.json"))
    qna_context = build_qna_context()

    # read pdf resume file
    try:
        resume_path = '/Users/jaswanth/mydocs/myprojects/langgraph/user_details/resume.pdf'
        if resume_path:
            resume_text = ""
            with open(resume_path, "rb") as f:
                reader = PdfReader(f)
                for page in reader.pages:
                    resume_text += page.extract_text() or ""
            user_profile += f"\n\nResume Text:\n{resume_text}"
    except Exception as e:
        console.print(f"[bold red]Error reading resume:[/bold red] {e}")

    worker_model = worker_model_holder.get("model")
    if worker_model is None:
        raise RuntimeError("worker_model_holder is not initialized — call initialize_tools() first.")

    from src.core.logging import setup_job_logger, log_event

    job_id = job_details.get("id", "Unknown")
    title = job_details.get("title", "Unknown position")
    company = job_details.get("companyName", "Unknown company")
    apply_url = job_details.get("link") or job_details.get("applyUrl")

    log_file = setup_job_logger(job_id, company, title)
    
    console.print(
        Panel(
            f"[bold cyan]Job ID:[/bold cyan] {job_id}\n"
            f"[bold cyan]Position:[/bold cyan] {title}\n"
            f"[bold cyan]Company:[/bold cyan] {company}\n"
            f"[bold cyan]URL:[/bold cyan] {apply_url}\n"
            f"[bold cyan]Log file:[/bold cyan] {log_file}",
            title=f"🤖 [bold green]Worker Started — Job {job_id}[/bold green]",
            border_style="cyan"
        )
    )

    prompt = f"""
        Apply for the Job:
        Job ID: {job_id}
        Job Title: {title}
        Company: {company}
        Apply URL: {apply_url}

        User Profile and Resume: {user_profile}

        Known user Q&A (these are user-confirmed answers only):
        {qna_context}
    """

    outcome = {
        "status": "failed",
        "failure_code": "worker_exception",
        "failure_detail": None,
        "last_completed_step": None,
        "retryable": True,
        "suggested_recovery_action": "Sign in to the existing candidate account and resume from the first incomplete field.",
    }
    checkpoint_store = None
    metric_url = apply_url
    metrics_started = False
    try:
        reset_auto_simplify_attempts()
        from src.application.metrics import (
            fetch_openrouter_credit_snapshot,
            start_application_metrics,
        )

        credit_snapshot = await asyncio.to_thread(fetch_openrouter_credit_snapshot)
        start_application_metrics(
            str(job_id),
            apply_url,
            credit_snapshot=credit_snapshot,
            model=MODEL_NAME,
        )
        metrics_started = True

        from src.application.checkpoint import ApplicationCheckpointStore
        checkpoint_store = ApplicationCheckpointStore()
        previous = checkpoint_store.load(str(job_id)) or {}
        outcome["last_completed_step"] = previous.get("last_completed_step") or previous.get("step_name")
        worker_graph = build_worker_graph()
        result = await worker_graph.ainvoke(
            {
                "messages": [
                    SystemMessage(content=WORKER_SYSTEM_PROMPT),
                    HumanMessage(content=prompt)
                ],
                "model": worker_model
            },
            config={"recursion_limit": 250}
        )

        last_message = result["messages"][-1].content if "messages" in result and result["messages"] else str(result)
        outcome.update({
            "status": "completed",
            "failure_code": None,
            "retryable": False,
            "suggested_recovery_action": "No recovery required.",
            "message": last_message,
        })
        console.print(f"[bold green]✅ Worker Finished Job {job_id}:[/bold green] {last_message}\n")

    except Exception as exc:
        outcome["failure_detail"] = str(exc)
        console.print(f"[bold red]❌ Worker Failed Job {job_id}:[/bold red] {exc}\n")
    finally:
        final_event = {"job_id": str(job_id), **outcome}
        log_event("APPLICATION_OUTCOME", final_event)
        if checkpoint_store is not None:
            try:
                previous = checkpoint_store.load(str(job_id)) or {}
                current_url = previous.get("url") or apply_url
                metric_url = current_url
                current_ats = previous.get("ats")
                if current_ats in (None, "", "unknown"):
                    current_ats = "workday" if "myworkdayjobs" in str(current_url).lower() else "unknown"
                checkpoint_store.record_step(
                    str(job_id),
                    ats=current_ats,
                    url=current_url,
                    failure_code=outcome["failure_code"],
                    failure_detail=outcome["failure_detail"],
                    last_completed_step=outcome["last_completed_step"],
                    retryable=outcome["retryable"],
                )
            except Exception as checkpoint_exc:
                log_event("CHECKPOINT_ERROR", {"failure_detail": str(checkpoint_exc)})
        if metrics_started:
            try:
                from src.application.metrics import (
                    fetch_openrouter_credit_snapshot,
                    finish_application_metrics,
                )

                credit_snapshot = await asyncio.to_thread(fetch_openrouter_credit_snapshot)
                metrics = finish_application_metrics(
                    outcome["status"],
                    company=company,
                    title=title,
                    credit_snapshot=credit_snapshot,
                    application_url=metric_url,
                )
                if metrics is not None:
                    log_event("APPLICATION_METRICS", metrics)
            except Exception as metrics_exc:
                # Metrics must not turn a completed application into a failure.
                log_event("APPLICATION_METRICS_ERROR", {"failure_detail": str(metrics_exc)})
    return {"job_id": str(job_id), "title": title, "company": company, **outcome}




@tool
def terminal(command: str):
    """Execute a terminal command and return its stdout (or stderr on failure)."""
    shell_tool = ShellTool()

    output = shell_tool.run(command)

    return output


search_tool = TavilySearch(max_results = 5, topic = "general", api_key = os.environ["TAVILY_API_KEY"])

@tool
def web_search(query: str):
    """Used to search the web for data"""
    result = search_tool.invoke({"query": query})

    return result

@tool
def update_file(file_name: str, old_string: str, new_string):
    """Used to edit the content of the file"""
    if not old_string:
        return (
            "Refused to replace an empty string: that would insert text between every "
            "character in the file. Use a specific existing string instead."
        )

    try:
        protected_file = Path(file_name).expanduser().resolve()
        is_qna_file = protected_file in {QNA_FILE_PATH.resolve(), PENDING_QUESTIONS_FILE_PATH.resolve()}
    except OSError:
        is_qna_file = False
    if is_qna_file:
        return "Do not edit Q&A or pending-question storage with update_file; use the dedicated recording tool instead."

    with open(file_name, 'r') as f:
        content = f.read()

    new_content = content.replace(old_string, new_string)

    with open(file_name, 'w') as f:
        f.write(new_content)

    
    console.print(f"[bold red]{old_string}[/bold red]")
    console.print(f"[bold green]{new_string}[/bold green]")

    return "Update finished"


@tool
def read_file(file_name : str):
    """Used to read the file"""

    try:
        protected_file = Path(file_name).expanduser().resolve()
        is_qna_file = protected_file in {QNA_FILE_PATH.resolve(), PENDING_QUESTIONS_FILE_PATH.resolve()}
    except OSError:
        is_qna_file = False
    if is_qna_file:
        return "Do not read Q&A or pending-question storage directly. The worker receives confirmed Q&A in its prompt."

    try:
        with open(file_name, 'r') as f:
            return f.read()

    except Exception as e:
        return f"File '{file_name}' could not be read or does not exist: {e}. If this was an optional skill file. "


@tool
async def simplify_autofill() -> str:
    """Trigger Simplify Autofill in the user's Chrome profile.

    The current application URL is opened in a Selenium-managed Google Chrome
    session that loads the user's installed Simplify extension and its signed-in
    state. Chrome remains open after success so the autofilled form can be
    reviewed in that same session.
    """
    from src.agent.app import mcp_manager
    from src.automation.simplify_selenium import SimplifyBrowserError, trigger_simplify_autofill

    try:
        output = await mcp_manager.call_tool(
            "playwright",
            "browser_run_code_unsafe",
            {"code": "async (page) => 'ACTIVE_APPLICATION_URL:' + page.url()"},
        )
    except Exception as exc:
        return f"SIMPLIFY_FAILED: Could not read the active application URL: {exc}"

    match = re.search(r"ACTIVE_APPLICATION_URL:(https?://[^\s\"']+)", str(output))
    if not match:
        return f"SIMPLIFY_FAILED: The active browser did not return an application URL. Details: {output}"

    try:
        result = await asyncio.to_thread(trigger_simplify_autofill, match.group(1))
    except SimplifyBrowserError as exc:
        return f"SIMPLIFY_FAILED: {exc}"
    except Exception as exc:
        return f"SIMPLIFY_FAILED: Unexpected Selenium error: {exc}"

    if result.changed_fields:
        return (
            f"SIMPLIFY_SUCCESS: Simplify Autofill populated {result.changed_fields} "
            "additional form control(s) in the Chrome-profile browser. Review the "
            "open Chrome window before continuing."
        )
    return (
        "SIMPLIFY_NO_CHANGES: Simplify's Autofill command ran in the open Chrome "
        "profile, but no additional controls changed. Check the Chrome window for "
        "a Simplify sign-in or review prompt."
    )

@tool
def get_jobs(filters: list[str] = None, n: int = None) -> list[dict]:
    """Fetch jobs from data/jobs.xlsx.

    Returns a list of job records sorted by fetched time (oldest first).
    Each record is a dict with keys like id, title, companyName, link,
    applyUrl, application_status, fetched_at, etc.
    Use this tool to get the queue of jobs to apply for.

    Args:
        filters: Optional list of status strings to filter by (e.g. ["Not Applied"], ["Applied"]).
                 If None, empty [], or containing "ALL", returns all jobs regardless of application_status
                 (including unassigned or blank status values).
        n: Optional maximum number of jobs to return. If None, returns all matching jobs.
    """
    if not _EXCEL_PATH.exists():
        return "No jobs file found. Run the job fetcher first."

    try:
        df = pd.read_excel(_EXCEL_PATH, dtype=str)
    except Exception as exc:
        return f"Could not read {_EXCEL_PATH}: {exc}"

    if df.empty:
        return []

    # Ensure application_status column exists and handle NaN/None/blank values
    if "application_status" not in df.columns:
        df["application_status"] = "Not Applied"

    status_cleaned = (
        df["application_status"]
        .fillna("Not Applied")
        .astype(str)
        .str.strip()
        .replace({"nan": "Not Applied", "None": "Not Applied", "": "Not Applied"})
    )
    df["application_status"] = status_cleaned

    # Filter logic: if filters is None, empty, or contains 'ALL', return all jobs
    if not filters or any(str(f).upper() == "ALL" for f in filters):
        pending = df.copy()
    else:
        filter_set = {str(f).strip() for f in filters if f}
        pending = df[df["application_status"].isin(filter_set)].copy()

    if "fetched_at" in pending.columns:
        pending["fetched_at"] = pd.to_datetime(pending["fetched_at"], errors="coerce")
        pending.sort_values("fetched_at", ascending=True, inplace=True)

    # Exclude massive description, metadata, and HTML blob columns to keep payload concise
    heavy_cols = {
        "descriptionHtml", "descriptionText", "companyDescription", 
        "companyAddress", "companyLogo", "inputUrl", "companySlogan", 
        "companyLinkedinUrl", "trackingId", "refId", "jobPosterName",
        "jobPosterTitle", "jobPosterPhoto", "jobPosterProfileUrl",
        "companyEmployeesCount", "benefits"
    }
    keep_cols = [c for c in pending.columns if c not in heavy_cols]

    records = pending[keep_cols].fillna("").to_dict(orient="records")

    if n is not None:
        return records[:n]

    return records

import threading

excel_lock = threading.Lock()


@tool
def update_job_status(job_id: str, status: str) -> str:
    """Update the application status of a job in data/jobs.xlsx by job id.

    Args:
        job_id: The ID of the job to update (e.g., '4447220072').
        status: The new status of the job application (e.g., 'Applied', 'Failed', 'In Progress').
    """
    with excel_lock:
        if not _EXCEL_PATH.exists():
            return f"No jobs file found at {_EXCEL_PATH}."

        try:
            from src.data.jobs_workbook import update_job_row
            update_job_row(
                _EXCEL_PATH,
                str(job_id).strip(),
                {"application_status": status},
            )
        except ValueError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            return f"Failed to save changes to {_EXCEL_PATH}: {exc}"

        return f"Successfully updated job '{job_id}' status to '{status}'."
