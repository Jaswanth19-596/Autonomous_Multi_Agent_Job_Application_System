import os
import re
import time
import asyncio
import sys
from dotenv import load_dotenv
from langchain_core.messages import ToolMessage, HumanMessage, AIMessage, SystemMessage
from prompt_toolkit.history import InMemoryHistory
from src.cli.commands import (
    build_session,
    prompt_for_input,
    prompt_for_input_async,
    is_command,
    dispatch,
    reset_history,
)
from rich.console import Console
from rich.markdown import Markdown
from rich.live import Live
from rich.spinner import Spinner

load_dotenv()

console = Console()
history = InMemoryHistory()


_RETRYABLE_TRANSPORT_MARKERS = (
    "read operation timed out",
    "readtimeout",
    "sslv3_alert_bad_record_mac",
    "bad record mac",
    "tlsv1 alert",
    "tls handshake timeout",
    "connection reset by peer",
    "connection aborted",
    "remoteprotocolerror",
    "server disconnected",
    "temporarily unavailable",
    "temporary failure",
    "broken pipe",
)


def _is_retryable_transport_error(error: Exception) -> bool:
    """Return whether retrying can recover a transient model/MCP connection error.

    In particular, ``bad record mac`` is a TLS record-integrity failure caused
    by a broken connection or intermediary.  It is safe to retry the *request*
    on a new connection, but certificate/configuration errors are deliberately
    excluded because retries cannot repair them.
    """
    text = str(error).lower()
    return any(marker in text for marker in _RETRYABLE_TRANSPORT_MARKERS)


def _is_transient_read_timeout(error: Exception) -> bool:
    """Recognize only read timeouts for existing callers."""
    text = str(error).lower()
    return "read operation timed out" in text or "readtimeout" in text


def _safe_to_retry_tool(tool_name: str) -> bool:
    """Limit automatic retries to idempotent browser operations.

    A failed click can leave a submission in an unknown state, so it must be
    reported to the worker for verification rather than clicked again.
    """
    return tool_name in {
        "playwright_browser_type",
        "playwright_browser_fill_form",
        "playwright_browser_evaluate",
        "playwright_browser_navigate",
        "playwright_browser_select_option",
        "playwright_browser_check",
        "playwright_browser_uncheck",
        "playwright_browser_file_upload",
    }


def _terminal_input_is_available() -> bool:
    """Return whether this process has an interactive terminal to read from.

    A launchd job has no usable stdin.  Some pseudo-terminal configurations
    still report ``isatty()`` as true, then prompt_toolkit raises EOFError;
    treat that the same as non-interactive input and wait on the control queue.
    """
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except (AttributeError, OSError):
        return False



# Tools that require explicit human approval before execution.
# Everything else is auto-approved.
DANGEROUS_TOOLS = {
    # "terminal",
    # "playwright_browser_install",
    # # "delegate_job_application",
    # # Gmail MCP tools
    # "gmail_send_email",
    # "gmail_draft_email",
    # "gmail_create_label",
    # "search_emails",
    # "get_email",
    # "send_email",
    # "draft_email",
    # "list_labels",
    # "create_label",
}




async def user_input_node(state):
    # Interactive REPL with pop-up autocomplete, styling & history
    from src.runtime.services import get_runtime

    runtime = get_runtime()
    remote_input = asyncio.create_task(runtime.inputs.messages.get())
    if not _terminal_input_is_available():
        # launchd supplies no usable stdin. The local control socket and
        # optional Telegram service feed this same remote-input queue.
        message = await remote_input
    else:
        terminal_input = None
        try:
            session = build_session(history)
            terminal_input = asyncio.ensure_future(prompt_for_input_async(session))
            done, pending = await asyncio.wait(
                {terminal_input, remote_input}, return_when=asyncio.FIRST_COMPLETED
            )
            if terminal_input in done:
                try:
                    message = terminal_input.result()
                except (EOFError, OSError):
                    # A detached service can look interactive initially but
                    # fail when it reads stdin. Keep the remote queue alive.
                    message = await remote_input
            else:
                message = remote_input.result()
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        except (EOFError, OSError):
            if terminal_input is not None:
                terminal_input.cancel()
                await asyncio.gather(terminal_input, return_exceptions=True)
            message = await remote_input

    # Dispatch registered slash commands directly (no LLM round-trip)
    if is_command(message):
        if message == "/clear":
            reset_history(history)
            dispatch("/clear")
            from langgraph.graph.message import REMOVE_ALL_MESSAGES, RemoveMessage
            from src.agent.app import MANAGER_SYSTEM_PROMPT

            return {
                "messages": [
                    RemoveMessage(id=REMOVE_ALL_MESSAGES),
                    SystemMessage(content=MANAGER_SYSTEM_PROMPT),
                ],
                "tool_calls": [],
                "approved": False,
                "plan_mode": False,
                "skip_execution": True,
                "queue_exhausted": False,
            }
        if message == "/plan":
            dispatch("/plan")
            return {
                "tool_calls": [],
                "approved": False,
                "plan_mode": True,
                "skip_execution": True,
                "queue_exhausted": False,
            }

        dispatch(message)
        return {
            "tool_calls": [],
            "approved": False,
            "skip_execution": True,
            "queue_exhausted": False,
        }

    await runtime.controller.set_task(message)
    await runtime.events.emit("task.started", {"task": message})
    return {
        "messages": [HumanMessage(content=message)],
        "skip_execution": False,
        "queue_exhausted": False,
    }


def user_input_condition(state):
    """Keep local slash commands out of the model execution loop."""
    return "user_input_node" if state.get("skip_execution") else "execution_node"

# def _prune_messages(messages: list, min_history_to_prune: int = 24) -> tuple[list, int]:
#     """Prunes heavy DOM inspection ToolMessages (snapshot, find, evaluate, run_code_unsafe, screenshot)
#     from older turns when conversation history exceeds `min_history_to_prune`.
#     Preserves recent turns and non-DOM message content intact.
#     """
#     if len(messages) <= min_history_to_prune:
#         return messages, 0

#     pruned_msgs = list(messages)
#     num_pruned = 0
#     PRUNABLE_TOOLS = {"snapshot", "find", "evaluate", "run_code_unsafe", "screenshot"}
#     STUB = "[Previous page DOM payload pruned to conserve context window]"

#     # Prune oldest DOM payloads, preserving the last 6 messages untouched
#     cutoff = max(0, len(pruned_msgs) - 6)
#     for i in range(cutoff):
#         msg = pruned_msgs[i]
#         if isinstance(msg, ToolMessage) and msg.content != STUB:
#             parent_ai = next(
#                 (pruned_msgs[j] for j in range(i - 1, -1, -1) if hasattr(pruned_msgs[j], "tool_calls") and pruned_msgs[j].tool_calls),
#                 None
#             )
#             if parent_ai:
#                 for tc in parent_ai.tool_calls:
#                     if tc.get("id") == msg.tool_call_id and any(tool in tc.get("name", "") for tool in PRUNABLE_TOOLS):
#                         pruned_msgs[i] = ToolMessage(content=STUB, tool_call_id=msg.tool_call_id)
#                         num_pruned += 1
#                         break

#     return pruned_msgs, num_pruned


async def execution_node(state, config=None):
    from src.runtime.services import get_runtime

    runtime = get_runtime()
    if not await runtime.controller.wait_if_paused():
        return {
            "messages": [HumanMessage(content="The user stopped the current autonomous task.")],
            "tool_calls": [],
        }
    full = None
    model = state.get("model")
    if model is None and config and "configurable" in config:
        model = config["configurable"].get("model")

    if model is None:
        from src.agent.app import manager_model
        model = manager_model

    from src.core.logging import get_job_prefix, log_event

    # pruned_msgs, num_pruned = _prune_messages(state["messages"])
    pruned_msgs, num_pruned = state["messages"], 0
    plan_mode = state.get("plan_mode", False)
    if plan_mode:
        planning_instruction = SystemMessage(
            content=(
                "Plan-only mode is active for this request. Give a concise, "
                "step-by-step plan, identify any needed user decisions, and do "
                "not call tools or execute actions."
            )
        )
        pruned_msgs = [*pruned_msgs[:-1], planning_instruction, pruned_msgs[-1]]
    if num_pruned > 0:
        prefix = get_job_prefix()
        console.print(f"{prefix}[dim cyan]⚡ Context optimized: pruned {num_pruned} old DOM payload(s)[/dim cyan]")
        log_event("TOKEN_OPT", f"Pruned {num_pruned} old DOM payload(s) from context window")

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        attempt_full = None
        try:
            with Live(console=console, refresh_per_second=10) as live:
                live.update(Spinner("dots", text=f"{get_job_prefix()}[bold cyan]Thinking...[/bold cyan]"))
                async for chunk in model.astream(pruned_msgs):
                    attempt_full = chunk if attempt_full is None else attempt_full + chunk
                    if chunk.content:
                        live.update(Markdown(attempt_full.content))
            full = attempt_full
            break
        except Exception as exc:
            if not _is_retryable_transport_error(exc) or attempt == max_attempts:
                raise
            delay_seconds = attempt
            console.print(
                f"{get_job_prefix()}[yellow]Model connection interrupted; retrying "
                f"({attempt}/{max_attempts}) in {delay_seconds}s…[/yellow]"
            )
            log_event(
                "MODEL_TRANSPORT_RETRY",
                {"attempt": attempt, "delay_seconds": delay_seconds, "error": str(exc)},
            )
            await asyncio.sleep(delay_seconds)

    if full and full.content:
        log_event("LLM_CONTENT", full.content)
        await runtime.events.emit("agent.message", {"content": full.content})

    return {
        "messages": [full],
        "tool_calls": full.tool_calls if full.tool_calls else [],
        "plan_mode": False if plan_mode else state.get("plan_mode", False),
    }


def format_tool_call(i, tool_call):
    from src.core.logging import redact_sensitive
    name = tool_call.get("name", "unknown_tool")
    args = redact_sensitive(tool_call.get("args", {}))
    return f"[bold cyan]{i}. {name}[/bold cyan]\n[dim]   Args:[/dim] {args}"


async def human_approval_node(state):

    dangerous_calls = [
        tc for tc in state["tool_calls"] if tc["name"] in DANGEROUS_TOOLS
    ]

    # If none of the pending tool calls are dangerous, auto-approve.
    if not dangerous_calls:
        return {"approved": True}

    from prompt_toolkit import PromptSession
    from src.runtime.services import get_runtime

    runtime = get_runtime()

    # Only show the dangerous tool calls that need approval.
    console.print("\n[bold red]⚠️  The agent wants to perform the following dangerous action(s):[/bold red]\n")

    for i, tool_call in enumerate(dangerous_calls):
        console.print(format_tool_call(i, tool_call))

    request = runtime.approvals.create_request(dangerous_calls)
    await runtime.events.emit(
        "approval.required",
        {"approval_id": request.id, "tool_calls": dangerous_calls},
    )

    terminal_input = asyncio.ensure_future(
        PromptSession().prompt_async("\nDo you approve the above operation : (y/n) ")
    )
    remote_decision = asyncio.create_task(runtime.approvals.wait_for(request.id))
    done, pending = await asyncio.wait(
        {terminal_input, remote_decision}, return_when=asyncio.FIRST_COMPLETED
    )
    if terminal_input in done:
        message = terminal_input.result().strip().lower()
        runtime.approvals.resolve(request.id, message in ("y", "yes"))
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    # If the request was resolved before the terminal answer, obtain its stored result
    # from the completed future; otherwise use the terminal decision.
    if remote_decision.done() and not remote_decision.cancelled():
        decision = remote_decision.result()
    else:
        decision = message in ("y", "yes") if terminal_input in done else False

    await runtime.events.emit(
        "approval.approved" if decision else "approval.denied",
        {"approval_id": request.id},
    )

    if decision:
        return {
            "messages": [HumanMessage(content="The user approved the tool execution. Go ahead.")],
            "approved": True
        }
    else:
        return {
            "messages": [HumanMessage(content="The user denied to give permission for the tool calls.")],
            "approved": False
        }



async def tool_node(state):
    from src.agent.app import mcp_manager
    from src.application.metrics import record_application_destination, record_tool_call
    from src.automation.simplify_auto import (
        FORM_SIGNATURE_CODE,
        claim_auto_simplify_attempt,
        form_signature_from_playwright_output,
    )
    from src.core.logging import get_job_prefix, log_event, redact_sensitive
    from src.application.resume_selection import (
        enforce_tailored_resume_paths,
        tailored_resume_requirement,
    )
    from src.agent.tools import tools_by_name
    from src.runtime.services import get_runtime

    # Async because MCP tools are coroutine-only StructuredTools; ainvoke also
    # covers the sync native tools by running them in an executor.
    tool_responses = []
    queue_exhausted = False
    prefix = get_job_prefix()
    runtime = get_runtime()

    async def auto_simplify_if_new_form(tool_name: str) -> str | None:
        """Run Simplify once when browser navigation reveals a distinct form."""
        if not tool_name.startswith("playwright_browser_"):
            return None
        try:
            signature_output = await mcp_manager.call_tool(
                "playwright", "browser_run_code_unsafe", {"code": FORM_SIGNATURE_CODE}
            )
            form = form_signature_from_playwright_output(str(signature_output))
            if form is None:
                return None
            signature, control_count = form
            if not claim_auto_simplify_attempt(signature):
                return None
            simplify = tools_by_name.get("simplify_autofill")
            if simplify is None:
                return "SIMPLIFY_AUTO_SKIPPED: simplify_autofill is unavailable."
            record_tool_call()
            console.print(
                f"{prefix}[bold yellow]🛠️  Automatically triggering Simplify "
                f"for {control_count} detected form controls[/bold yellow]"
            )
            result = await simplify.ainvoke({})
            log_event("AUTO_SIMPLIFY", {"control_count": control_count, "result": str(result)})
            requirement = tailored_resume_requirement()
            return f"{result}\n\n{requirement}" if requirement else str(result)
        except Exception as exc:
            # Detection is an optimization. The normal worker can still inspect
            # and complete the form if an ATS rejects page inspection.
            log_event("AUTO_SIMPLIFY_ERROR", {"failure_detail": str(exc)})
            return None

    for tool_call in state["tool_calls"]:
        if not await runtime.controller.wait_if_paused():
            tool_responses.append(
                ToolMessage(
                    content="Tool execution skipped because the user stopped the task.",
                    tool_call_id=tool_call["id"],
                )
            )
            continue
        record_tool_call()
        await runtime.controller.set_tool(tool_call["name"])
        effective_args = enforce_tailored_resume_paths(tool_call.get("args", {}))
        tailored_resume_path_enforced = effective_args != tool_call.get("args", {})
        if tailored_resume_path_enforced:
            log_event(
                "TAILORED_RESUME_PATH_ENFORCED",
                {"tool": tool_call["name"], "args": effective_args},
            )
        safe_args = redact_sensitive(effective_args)
        await runtime.events.emit(
            "tool.started", {"tool": tool_call["name"], "args": safe_args, "prefix": prefix}
        )
        log_event(
            "TOOL_CALL",
            {
                "tool": tool_call["name"],
                "args": safe_args,
            },
        )

        if tool_call["name"] not in tools_by_name:
            result = (
                f"Error: no such tool '{tool_call['name']}'. Available"
                f" tools: {', '.join(sorted(tools_by_name))}"
            )
            log_event("TOOL_ERROR", result)
            await runtime.events.emit(
                "tool.failed", {"tool": tool_call["name"], "args": safe_args, "error": result, "prefix": prefix}
            )
        else:
            tool = tools_by_name[tool_call["name"]]
            try:
                # A model can otherwise start filling immediately after a page
                # transition without taking another snapshot. Run the form-step
                # check before any action that could fill or script-fill fields.
                pre_auto_simplify_result = None
                if tool_call["name"] in {
                    "playwright_browser_fill_form",
                    "playwright_browser_file_upload",
                    "playwright_browser_run_code_unsafe",
                }:
                    pre_auto_simplify_result = await auto_simplify_if_new_form(
                        tool_call["name"]
                    )
                # A retry starts a new MCP connection but keeps the existing
                # Chrome tab and already-filled controls.  Never retry clicks:
                # a submit may have reached the ATS despite its failed reply.
                max_tool_attempts = 3 if _safe_to_retry_tool(tool_call["name"]) else 1
                for tool_attempt in range(1, max_tool_attempts + 1):
                    try:
                        result = await tool.ainvoke(effective_args)
                        break
                    except Exception as exc:
                        if (
                            tool_attempt == max_tool_attempts
                            or not _is_retryable_transport_error(exc)
                        ):
                            raise
                        delay_seconds = tool_attempt
                        console.print(
                            f"{prefix}[yellow]Browser connection interrupted; retrying "
                            f"{tool_call['name']} ({tool_attempt}/{max_tool_attempts}) "
                            f"in {delay_seconds}s…[/yellow]"
                        )
                        log_event(
                            "TOOL_TRANSPORT_RETRY",
                            {
                                "tool": tool_call["name"],
                                "attempt": tool_attempt,
                                "delay_seconds": delay_seconds,
                                "error": str(exc),
                            },
                        )
                        await asyncio.sleep(delay_seconds)
                if tool_call["name"] == "playwright_browser_navigate":
                    record_application_destination(effective_args.get("url"))
                    destination = re.search(r"Page URL:\s*(https?://[^\s)]+)", str(result))
                    if destination:
                        record_application_destination(destination.group(1))
                auto_simplify_result = (
                    pre_auto_simplify_result
                    or await auto_simplify_if_new_form(tool_call["name"])
                )
                if auto_simplify_result:
                    result = f"{result}\n\n{auto_simplify_result}"
                if tailored_resume_path_enforced:
                    requirement = tailored_resume_requirement()
                    result = f"{result}\n\n{requirement}" if requirement else result
                if tool_call["name"] == "get_jobs" and isinstance(result, list) and not result:
                    # No more work is a normal idle state, not a reason for
                    # the manager model to call get_jobs until recursion ends.
                    queue_exhausted = True
                log_event("TOOL_RESULT", str(result))
                await runtime.events.emit(
                    "tool.completed",
                    {
                        "tool": tool_call["name"],
                        "args": safe_args,
                        "result": str(result),
                        "notify_completion": tool_call["name"] in {"delegate_job_application", "update_job_status"},
                    },
                )
            except Exception as e:
                # Report the failure back to the model instead of killing the session.
                result = f"Error: tool '{tool_call['name']}' failed: {e}"
                log_event("TOOL_ERROR", str(e))
                await runtime.events.emit(
                    "tool.failed",
                    {"tool": tool_call["name"], "args": safe_args, "error": str(e), "prefix": prefix},
                )

        tool_responses.append(
            ToolMessage(content=str(result), tool_call_id=tool_call["id"])
        )
        await runtime.controller.set_tool(None)

    return {"messages": tool_responses, "queue_exhausted": queue_exhausted}










    
