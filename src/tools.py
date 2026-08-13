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

warnings.filterwarnings("ignore", category=UserWarning, module="langchain_community.tools.shell.tool")
warnings.filterwarnings("ignore", message=".*shell tool has no safeguards.*")

load_dotenv()


console = Console()

tools_by_name = {}
worker_model_holder = {"model": None}


from rich.panel import Panel
from src.ui_qna import interactive_ask_user, interactive_collect_fields, update_qna_file
from src.simplify_gate import (
    PAGE_FINGERPRINT_CODE,
    SIMPLIFY_SIDE_PANEL_AUTOFILL_CODE,
    authorize_simplify,
    is_simplify_authorized,
    is_simplify_unsupported,
    mark_simplify_unsupported,
    parse_playwright_json,
    reset_simplify_authorization,
    simplify_result_authorizes_repairs,
)
from src.form_batch import CLICK_NEXT_CONTROL_CODE, FORM_INSPECTION_CODE, build_batch_repair_code
from src.application_semantics import (
    AUDIT_PAGE_CODE,
    DROPDOWNS_CODE,
    PAGE_SCHEMA_CODE,
    RADIO_GROUPS_CODE,
    CandidateProfileStore,
    build_advance_code,
    build_fill_page_code,
    build_fill_dropdowns_code,
    build_fill_radio_groups_code,
    build_upload_code,
    resolve_answers,
)
from src.workday_controls import build_select_workday_combobox_code


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
async def delegate_job_application(job_details: dict) -> dict:
    """Delegate a single job application to a worker subagent.
    The worker gets exclusive access to the browser. Jobs are processed one at a time.

    Args:
        job_details: Dict containing the full job record from get_jobs (must include 'id', 'title', 'companyName', and 'link' or 'applyUrl').
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
    # A new delegated job starts a fresh Simplify-support decision.
    reset_simplify_authorization()

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
    try:
        from src.application_checkpoint import ApplicationCheckpointStore
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


@tool
async def simplify_autofill() -> str:
    """Trigger Simplify Autofill on the current application page.

    This is the only tool that resolves the Simplify-first gate. It searches
    only Simplify-owned open shadow roots, clicks an accessible Autofill
    control, waits for the extension to settle, and records page-scoped
    authorization. If Simplify is unavailable, it authorizes manual fallback
    on this exact page/form step.
    """
    from src.app import mcp_manager

    # Enforce once-per-form-step even if the model asks repeatedly. A stable
    # fingerprint remains authorized across ordinary field edits and rerenders.
    try:
        fingerprint_output = await mcp_manager.call_tool(
            "playwright",
            "browser_run_code_unsafe",
            {"code": PAGE_FINGERPRINT_CODE},
        )
        current_fingerprint = parse_playwright_json(fingerprint_output)["fingerprint"]
        if is_simplify_unsupported(current_fingerprint):
            authorize_simplify(
                current_fingerprint,
                "Manual fallback: Simplify panel absent on this ATS origin",
            )
        if is_simplify_authorized(current_fingerprint):
            return (
                "SIMPLIFY_ALREADY_ATTEMPTED: This exact form step is already "
                "authorized. Do not call Simplify again; continue the existing "
                "repair plan."
            )
    except Exception:
        # The normal Simplify path below retains its own inspection and error
        # recovery, so a failed preflight must not make the application fail.
        pass

    # Revoke the prior page's authorization, but preserve ATS origins already
    # proven unsupported during this job application.
    reset_simplify_authorization(clear_unsupported=False)
    try:
        output = await mcp_manager.call_tool(
            "playwright",
            "browser_run_code_unsafe",
            {"code": SIMPLIFY_SIDE_PANEL_AUTOFILL_CODE},
        )
        result = parse_playwright_json(output)
    except Exception as exc:
        reason = f"Could not inspect Simplify: {exc}"
        try:
            fingerprint_output = await mcp_manager.call_tool(
                "playwright",
                "browser_run_code_unsafe",
                {"code": PAGE_FINGERPRINT_CODE},
            )
            fingerprint = parse_playwright_json(fingerprint_output)["fingerprint"]
            authorize_simplify(fingerprint, f"Manual fallback: {reason}")
            return (
                f"SIMPLIFY_MANUAL_FALLBACK: {reason} Manual form filling is "
                "authorized on this exact page/form step."
            )
        except Exception as fingerprint_exc:
            return (
                f"SIMPLIFY_UNAVAILABLE: {reason} Could not establish page-scoped "
                f"manual fallback: {fingerprint_exc}"
            )

    if not simplify_result_authorizes_repairs(result):
        reason = result.get("reason", "Autofill was not verifiably clicked")
        simplify_text = result.get("simplify_text", "").strip()
        detail = f" Simplify UI: {simplify_text}" if simplify_text else ""
        fingerprint = result.get("fingerprint")
        if fingerprint:
            if result.get("status") == "unavailable" and result.get("simplify_present") is False:
                mark_simplify_unsupported(fingerprint)
            authorize_simplify(fingerprint, f"Manual fallback: {reason}")
            return (
                f"SIMPLIFY_MANUAL_FALLBACK: {reason}.{detail} Manual form "
                "filling is authorized on this exact page/form step."
            )
        return (
            f"SIMPLIFY_UNAVAILABLE: {reason}.{detail} "
            "Could not establish page-scoped manual fallback."
        )

    changed_fields = result.get("changed_fields", 0)
    completed_without_new_changes = changed_fields == 0
    evidence = (
        f"Clicked Simplify control: {result.get('control', 'Autofill')}; "
        f"changed fields: {changed_fields}"
    )
    authorize_simplify(result["fingerprint"], evidence)
    if completed_without_new_changes:
        return (
            "SIMPLIFY_SUCCESS: Simplify reports Autofill complete on the current "
            "page. It changed no additional fields on this repeated attempt; "
            "scan once and manually repair the fields Simplify marked for review."
        )
    return (
        f"SIMPLIFY_SUCCESS: Autofill changed {changed_fields} field(s) on the "
        "current page. Scan once, then manually repair only fields Simplify "
        "marked for review, missing, or incorrect."
    )


async def _authorized_page_fingerprint() -> tuple[str | None, str | None]:
    """Resolve and validate the current page before a high-level form action."""
    from src.app import mcp_manager

    output = await mcp_manager.call_tool(
        "playwright", "browser_run_code_unsafe", {"code": PAGE_FINGERPRINT_CODE}
    )
    fingerprint = parse_playwright_json(output)["fingerprint"]
    if is_simplify_unsupported(fingerprint):
        authorize_simplify(
            fingerprint, "Manual fallback: Simplify panel absent on this ATS origin"
        )
    if not is_simplify_authorized(fingerprint):
        return None, (
            "BLOCKED_BY_SIMPLIFY_GATE: Run simplify_autofill on this exact form "
            "step before inspecting or repairing it."
        )
    return fingerprint, None


@tool
async def inspect_application_form() -> str:
    """Inspect the current authorized form once in a structured, token-efficient call.

    Returns every visible input with its key, label, type, current value,
    required state, and available options. Custom comboboxes are opened one at
    a time inside this single browser execution so all option lists are returned
    together. Call once after Simplify, then create one complete repair plan.
    """
    from src.app import mcp_manager

    _, error = await _authorized_page_fingerprint()
    if error:
        return error
    output = await mcp_manager.call_tool(
        "playwright", "browser_run_code_unsafe", {"code": FORM_INSPECTION_CODE}
    )
    result = parse_playwright_json(output)
    return json.dumps({"controls": result.get("controls", [])}, ensure_ascii=False)


@tool
async def batch_repair_application_form(repairs: list[dict]) -> str:
    """Execute a complete repair plan for the current authorized form in one call.

    Each repair must contain `key` or `label`, `value`, and optionally `type`
    (`text`, `textarea`, `select`, `combobox`, `checkbox`, or `radio`). Use keys
    and exact option values returned by inspect_application_form. Text fields,
    native selects, custom comboboxes, checkboxes, and radios are processed
    sequentially inside one browser execution. Returns only filled/unresolved
    results; manually handle only unresolved items.
    """
    from src.app import mcp_manager

    if not repairs:
        return json.dumps({"results": [], "message": "No repairs requested"})
    _, error = await _authorized_page_fingerprint()
    if error:
        return error
    code = build_batch_repair_code(json.dumps(repairs, ensure_ascii=False))
    output = await mcp_manager.call_tool(
        "playwright", "browser_run_code_unsafe", {"code": code}
    )
    result = parse_playwright_json(output)
    return json.dumps({"results": result.get("results", [])}, ensure_ascii=False)


@tool
async def click_application_next() -> str:
    """Click the current form's Next/Continue/forward-arrow control in one call.

    Use this instead of searching or inspecting an icon-only navigation button.
    It resolves accessible labels plus unlabeled Dojo/widget buttons and
    right-arrow/chevron descendants, rejects Back/Previous controls, and clicks
    the highest-confidence visible clickable ancestor.
    """
    from src.app import mcp_manager

    _, error = await _authorized_page_fingerprint()
    if error:
        return error
    output = await mcp_manager.call_tool(
        "playwright", "browser_run_code_unsafe", {"code": CLICK_NEXT_CONTROL_CODE}
    )
    result = parse_playwright_json(output)
    return json.dumps(
        {key: result.get(key) for key in ("clicked", "identity", "score", "reason") if key in result},
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# Semantic application tools (preferred over raw Playwright primitives)
# ---------------------------------------------------------------------------

_CANDIDATE_PROFILE_PATH = Path(__file__).resolve().parent.parent / "user_details" / "candidate_profile.json"


@tool
def save_application_checkpoint(job_id: str, state: dict) -> str:
    """Save a non-sensitive checkpoint after a successfully verified application step."""
    from src.application_checkpoint import ApplicationCheckpointStore
    return json.dumps(ApplicationCheckpointStore().record_step(job_id, **state), ensure_ascii=False)


@tool
def load_application_checkpoint(job_id: str) -> str:
    """Load resume metadata so an interrupted application continues from its first incomplete field."""
    from src.application_checkpoint import ApplicationCheckpointStore
    checkpoint = ApplicationCheckpointStore().load(job_id)
    return json.dumps({"checkpoint": checkpoint, "resume_existing_account": bool(checkpoint)}, ensure_ascii=False)


async def _run_semantic_browser(code: str) -> dict:
    from src.app import mcp_manager
    output = await mcp_manager.call_tool(
        "playwright", "browser_run_code_unsafe", {"code": code}
    )
    return parse_playwright_json(output)


@tool
async def inspect_application_page() -> str:
    """Return one compact semantic schema for the current application page.

    Includes ATS, progress, fields, option lists, validation errors, upload
    controls, actions, and CAPTCHA presence. Requires the Simplify gate first.
    Prefer this over snapshots, find, evaluate, and inspect_application_form.
    """
    _, error = await _authorized_page_fingerprint()
    if error:
        return error
    return json.dumps(await _run_semantic_browser(PAGE_SCHEMA_CODE), ensure_ascii=False)


@tool
async def inspect_radio_groups() -> str:
    """Identify every visible radio question and all of its options in one call."""
    _, error = await _authorized_page_fingerprint()
    if error:
        return error
    return json.dumps(await _run_semantic_browser(RADIO_GROUPS_CODE), ensure_ascii=False)


@tool
async def fill_radio_groups(selections: list[dict]) -> str:
    """Select and verify radio answers using keys/options from inspect_radio_groups."""
    if not selections:
        return json.dumps({"results": [], "message": "No radio selections supplied"})
    _, error = await _authorized_page_fingerprint()
    if error:
        return error
    return json.dumps(await _run_semantic_browser(build_fill_radio_groups_code(selections)), ensure_ascii=False)


@tool
async def inspect_dropdowns() -> str:
    """Identify every visible native or custom dropdown and all options in one call."""
    _, error = await _authorized_page_fingerprint()
    if error:
        return error
    return json.dumps(await _run_semantic_browser(DROPDOWNS_CODE), ensure_ascii=False)


@tool
async def fill_dropdowns(selections: list[dict]) -> str:
    """Select and verify dropdown answers using keys/options from inspect_dropdowns."""
    if not selections:
        return json.dumps({"results": [], "message": "No dropdown selections supplied"})
    _, error = await _authorized_page_fingerprint()
    if error:
        return error
    return json.dumps(await _run_semantic_browser(build_fill_dropdowns_code(selections)), ensure_ascii=False)


@tool
async def select_workday_combobox(control_id: str, desired_option: str) -> str:
    """Commit and verify an exact option in a searchable Workday combobox.

    ``control_id`` is the stable textbox id (for example ``source--source``),
    without a transient snapshot reference. Typed search text alone is never
    accepted as a successful selection.
    """
    _, error = await _authorized_page_fingerprint()
    if error:
        return error
    result = await _run_semantic_browser(
        build_select_workday_combobox_code(control_id, desired_option)
    )
    return json.dumps(result, ensure_ascii=False)


@tool
async def fill_application_page(answers: dict) -> str:
    """Semantically match, fill, and verify all supplied page answers in one call.

    Keys should be human field names (for example ``State`` or
    ``work_authorization``), not transient element references. Returns only a
    per-answer verified/unresolved result. Never guesses missing answers.
    """
    if not answers:
        return json.dumps({"results": [], "message": "No answers supplied"})
    _, error = await _authorized_page_fingerprint()
    if error:
        return error
    result = await _run_semantic_browser(build_fill_page_code(answers))
    return json.dumps(result, ensure_ascii=False)


@tool
async def audit_application_page() -> str:
    """Audit the current page for required, invalid, and server-error fields.

    Call after filling and before advancing. The result states whether the page
    is ready and lists only actionable problems, avoiding another DOM snapshot.
    """
    _, error = await _authorized_page_fingerprint()
    if error:
        return error
    return json.dumps(await _run_semantic_browser(AUDIT_PAGE_CODE), ensure_ascii=False)


@tool
async def upload_application_document(document_type: str, path: str) -> str:
    """Upload and verify a resume, cover letter, transcript, or other document.

    Locates hidden file inputs semantically, uploads directly, and verifies the
    browser's selected filename without opening a blocking file chooser.
    """
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        return json.dumps({"uploaded": False, "reason": f"File not found: {resolved}"})
    _, error = await _authorized_page_fingerprint()
    if error:
        return error
    result = await _run_semantic_browser(build_upload_code(str(resolved), document_type))
    return json.dumps(result, ensure_ascii=False)


@tool
async def advance_application(action: str = "continue", require_valid_page: bool = True) -> str:
    """Audit and perform a guarded Continue/Next action in one call.

    ``submit`` is deliberately rejected; final submission must remain an
    explicit browser action after the user/application policy authorizes it.
    """
    normalized = action.strip().lower()
    if normalized == "submit":
        return "SUBMIT_REQUIRES_EXPLICIT_ACTION: audit first, then use the separately approved submit control."
    if normalized not in {"continue", "next", "proceed"}:
        return json.dumps({"advanced": False, "reason": "Unsupported action"})
    _, error = await _authorized_page_fingerprint()
    if error:
        return error
    if require_valid_page:
        audit = await _run_semantic_browser(AUDIT_PAGE_CODE)
        if not audit.get("ready_to_continue"):
            return json.dumps({"advanced": False, "reason": "page_not_ready", "audit": audit}, ensure_ascii=False)
    result = await _run_semantic_browser(build_advance_code(normalized))
    return json.dumps(result, ensure_ascii=False)


@tool
def resolve_application_answers(fields: list[dict], profile: dict | None = None) -> str:
    """Resolve form fields from the candidate profile with source provenance.

    Returns resolved answers, missing required data, and sensitive questions
    that require explicit candidate authorization. It never fabricates values.
    """
    stored = CandidateProfileStore(_CANDIDATE_PROFILE_PATH).plain_values()
    if profile:
        stored.update(profile)
    return json.dumps(resolve_answers(fields, stored), ensure_ascii=False)


@tool
def update_candidate_profile(values: dict, source: str = "user", reusable: bool = True) -> str:
    """Persist user-provided application answers with provenance and reuse consent."""
    if not values:
        return "PROFILE_UNCHANGED: no values supplied"
    data = CandidateProfileStore(_CANDIDATE_PROFILE_PATH).update(values, source, reusable)
    return json.dumps({"updated": sorted(values), "version": data.get("version", 1)}, ensure_ascii=False)


@tool
def ask_for_missing_application_data(title: str, fields: list[dict], repeat: int = 1) -> str:
    """Collect missing application data through typed, structured prompts.

    Each field accepts ``key``, optional ``label``, and ``required``. Use
    ``repeat=3`` for three references. Unlike ask_user, this never substitutes
    generic Yes/No choices for required free-form values.
    """
    if not fields or repeat < 1 or repeat > 20:
        return json.dumps({"error": "fields are required and repeat must be 1..20"})
    values = interactive_collect_fields(title, fields, repeat)
    return json.dumps({"title": title, "values": values}, ensure_ascii=False)

# ---------------------------------------------------------------------------
# Workday skills automation tool
# ---------------------------------------------------------------------------

@tool
async def fill_workday_skills(selector: str, skills: list[str]) -> str:
    """Fill Workday's searchable Skills combobox. Types each skill, waits for
    autocomplete suggestions, and clicks the top result. Deterministic — no AI.

    Call this when you encounter Workday's Skills section with a searchable
    input. Pass the CSS selector of the input element and all skills to add.

    Args:
        selector: CSS selector for the skills search input (e.g. 'input[placeholder*=\"Search\"]', '#skillsInput').
        skills: List of skill names to add (e.g. ["Python", "Machine Learning", "AWS"]).
    """
    import json as _json
    from src.app import mcp_manager

    skills_json = _json.dumps(skills)
    escaped_selector = selector.replace("'", "\\'")

    code = f"""
const skills = {skills_json};
const selector = '{escaped_selector}';
const results = [];

for (const skill of skills) {{
    // Click the input and clear it
    const input = page.locator(selector);
    await input.click();
    await input.fill('');
    await page.waitForTimeout(200);

    // Type the skill name
    await input.fill(skill);
    await page.waitForTimeout(1000);

    // Try to find and click the first suggestion in the dropdown
    const option = page.locator('[role="listbox"] [role="option"]').first();
    try {{
        await option.waitFor({{ state: 'visible', timeout: 3000 }});
        const optionText = await option.textContent();
        await option.click();
        results.push('Added: ' + skill + ' (selected: ' + optionText.trim() + ')');
    }} catch (e) {{
        // Fallback: press Enter to accept whatever is typed
        await page.keyboard.press('Enter');
        results.push('Added: ' + skill + ' (pressed Enter — no dropdown)');
    }}

    await page.waitForTimeout(500);
}}

return results.join('\\n');
"""

    try:
        result = await mcp_manager.call_tool('playwright', 'run_code_unsafe', {'code': code})
        return f"Skills filled successfully:\n{result}"
    except Exception as e:
        return f"Error filling skills: {e}"


# ---------------------------------------------------------------------------
# Job queue tools
# ---------------------------------------------------------------------------
import pandas as pd
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent
_EXCEL_PATH = _BASE_DIR / "data" / "jobs.xlsx"
_JOBBOARD_SKILLS_DIR = _BASE_DIR / "skills" / "jobboards"


@tool
def update_jobboard_skill(platform: str, learnings: list[str]) -> str:
    """Create or append reusable learnings to a job-board skill file.

    This tool is restricted to `skills/jobboards/<platform>.md`. Use the actual
    ATS reached after clicking Apply (for example Workday, Greenhouse, Ashby,
    SuccessFactors, ADP), not LinkedIn merely because it supplied the job link.
    Include only platform-general, verified techniques; never include company,
    job, candidate, credentials, generated element IDs, or one-off answers.

    Args:
        platform: Job-board/ATS name, using letters, numbers, spaces, `_`, or `-`.
        learnings: Concise reusable platform-general bullet points.
    """
    slug = re.sub(r"[^a-z0-9_-]+", "-", platform.strip().lower()).strip("-_")
    if not slug or not learnings:
        return "SKILL_NOT_UPDATED: platform and at least one learning are required."
    _JOBBOARD_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    skill_path = _JOBBOARD_SKILLS_DIR / f"{slug}.md"
    existing = skill_path.read_text(encoding="utf-8") if skill_path.exists() else ""
    normalized_existing = {line.strip().lower() for line in existing.splitlines()}
    additions = []
    for learning in learnings:
        text = " ".join(str(learning).strip().split())
        if not text:
            continue
        bullet = text if text.startswith("- ") else f"- {text}"
        if bullet.lower() not in normalized_existing:
            additions.append(bullet)
            normalized_existing.add(bullet.lower())
    if not additions:
        return f"SKILL_UNCHANGED: No new learnings for {skill_path.relative_to(_BASE_DIR)}"
    heading = existing.rstrip() if existing.strip() else f"# {platform.strip()} job-board skill"
    skill_path.write_text(f"{heading}\n" + "\n".join(additions) + "\n", encoding="utf-8")
    return (
        f"SKILL_UPDATED: {skill_path.relative_to(_BASE_DIR)} "
        f"with {len(additions)} reusable learning(s)."
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
            # Strip control characters forbidden in Excel XML
            df = df.map(lambda x: re.sub(r'[\000-\010]|[\013-\014]|[\016-\037]', '', x) if isinstance(x, str) else x)
            df.to_excel(_EXCEL_PATH, index=False)
        except Exception as exc:
            return f"Failed to save changes to {_EXCEL_PATH}: {exc}"

        return f"Successfully updated job '{job_id}' status to '{status}'."
