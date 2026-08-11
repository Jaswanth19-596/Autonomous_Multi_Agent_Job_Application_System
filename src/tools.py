import os
import asyncio
import warnings
from dotenv import load_dotenv

from langchain_community.tools import ShellTool
from langchain_core.tools import tool
from langchain_tavily import TavilySearch
from rich.console import Console
from langchain_core.messages import SystemMessage, HumanMessage

warnings.filterwarnings("ignore", category=UserWarning, module="langchain_community.tools.shell.tool")
warnings.filterwarnings("ignore", message=".*shell tool has no safeguards.*")

load_dotenv()


console = Console()

tools_by_name = {}
worker_model_holder = {"model": None}


from rich.panel import Panel

@tool
async def delegate_job_application(job_details: dict) -> str:
    """Delegate a single job application to a worker subagent.
    The worker gets exclusive access to the browser. Jobs are processed one at a time.

    Args:
        job_details: Dict containing the full job record from get_pending_jobs (must include 'id', 'title', 'companyName', and 'link' or 'applyUrl').
    """
    from src.app import build_worker_graph, WORKER_SYSTEM_PROMPT, user_profile

    worker_model = worker_model_holder.get("model")
    if worker_model is None:
        raise RuntimeError("worker_model_holder is not initialized — call initialize_tools() first.")

    from src.logger import setup_job_logger, log_event

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

    worker_graph = build_worker_graph()

    prompt = f"""
        Apply for the Job:
        Job ID: {job_id}
        Job Title: {title}
        Company: {company}
        Apply URL: {apply_url}

        User Profile and Resume: {user_profile}
    """

    try:
        result = await worker_graph.ainvoke(
            {
                "messages": [
                    SystemMessage(content=WORKER_SYSTEM_PROMPT),
                    HumanMessage(content=prompt)
                ],
                "model": worker_model
            },
            config={"recursion_limit": 200}
        )

        last_message = result["messages"][-1].content if "messages" in result and result["messages"] else str(result)
        console.print(f"[bold green]✅ Worker Finished Job {job_id}:[/bold green] {last_message}\n")
        return f"Job ID {job_id} ({title} at {company}) status: {last_message}"

    except Exception as exc:
        console.print(f"[bold red]❌ Worker Failed Job {job_id}:[/bold red] {exc}\n")
        return f"Job ID {job_id} ({title} at {company}) FAILED: {exc}"




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
        with open(file_name, 'r') as f:
            return f.read()

    except Exception as e:
        return f"File '{file_name}' could not be read or does not exist: {e}. If this was an optional skill file. "


# ---------------------------------------------------------------------------
# Job queue tools
# ---------------------------------------------------------------------------
import pandas as pd
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent
_EXCEL_PATH = _BASE_DIR / "data" / "jobs.xlsx"


@tool
def get_pending_jobs() -> list[dict]:
    """Fetch jobs from data/jobs.xlsx that have not been applied to yet.

    Returns a list of job records sorted by fetched time (oldest first).
    Each record is a dict with keys like id, title, companyName, link,
    applyUrl, application_status, fetched_at, etc.
    Use this tool to get the queue of jobs to apply for.
    """
    if not _EXCEL_PATH.exists():
        return "No jobs file found. Run the job fetcher first."

    try:
        df = pd.read_excel(_EXCEL_PATH, dtype=str)
    except Exception as exc:
        return f"Could not read {_EXCEL_PATH}: {exc}"

    if "application_status" not in df.columns:
        pending = df.copy()
    else:
        pending = df[df["application_status"].isin(["Not Applied", "In Progress"])].copy()

    if "fetched_at" in pending.columns:
        pending["fetched_at"] = pd.to_datetime(pending["fetched_at"], errors="coerce")
        pending.sort_values("fetched_at", ascending=True, inplace=True)

    # Exclude massive description and HTML blob columns to keep payload concise
    heavy_cols = {
        "descriptionHtml", "descriptionText", "companyDescription", 
        "companyAddress", "companyLogo", "inputUrl", "companySlogan", 
        "companyLinkedinUrl"
    }
    keep_cols = [c for c in pending.columns if c not in heavy_cols]

    return pending[keep_cols].to_dict(orient="records")


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
            df = pd.read_excel(_EXCEL_PATH, dtype=str)
        except Exception as exc:
            return f"Could not read {_EXCEL_PATH}: {exc}"

        if "id" not in df.columns:
            return f"Error: 'id' column missing in {_EXCEL_PATH}."

        if "application_status" not in df.columns:
            df["application_status"] = "Not Applied"

        target_id = str(job_id).strip()
        mask = df["id"].astype(str).str.strip() == target_id

        if not mask.any():
            return f"Job with ID '{job_id}' not found in {_EXCEL_PATH}."

        df.loc[mask, "application_status"] = status

        try:
            df.to_excel(_EXCEL_PATH, index=False)
        except Exception as exc:
            return f"Failed to save changes to {_EXCEL_PATH}: {exc}"

        return f"Successfully updated job '{job_id}' status to '{status}'."