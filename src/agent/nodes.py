import os
import re
import time
import asyncio
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
    COMMANDS,
    run_help,
)
from rich.console import Console
from rich.markdown import Markdown
from rich.live import Live
from rich.spinner import Spinner

load_dotenv()

console = Console()
history = InMemoryHistory()


def _is_transient_read_timeout(error: Exception) -> bool:
    """Recognize retryable transport timeouts from model/MCP streaming."""
    text = str(error).lower()
    return "read operation timed out" in text or "readtimeout" in text



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
    session = build_session(history)
    from src.runtime.services import get_runtime

    runtime = get_runtime()
    terminal_input = asyncio.ensure_future(prompt_for_input_async(session))
    remote_input = asyncio.create_task(runtime.inputs.messages.get())
    done, pending = await asyncio.wait(
        {terminal_input, remote_input}, return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    message = next(iter(done)).result()

    # Dispatch registered slash commands directly (no LLM round-trip)
    if is_command(message):
        if message == "/index":
            dispatch("/index")
        elif message == "/help":
            run_help()
        elif message == "/clear":
            reset_history(history)
            dispatch("/clear")
            # Reset graph state: wipe messages & tool calls
            return {
                "messages": [
                    HumanMessage(content=f"The user ran `{message}` — state has been reset.")
                ],
                "tool_calls": [],
                "approved": False,
            }
        elif message == "/plan":
            dispatch("/plan")
        else:
            dispatch(message)

        # Other slash commands simply loop back to the prompt
        return {
            "messages": [HumanMessage(content=f"The user ran the slash command `{message}`.")],
            "tool_calls": [],
            "approved": False,
        }

    await runtime.controller.set_task(message)
    await runtime.events.emit("task.started", {"task": message})
    return {"messages": [HumanMessage(content=message)]}

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
            if not _is_transient_read_timeout(exc) or attempt == max_attempts:
                raise
            delay_seconds = attempt
            console.print(
                f"{get_job_prefix()}[yellow]Model read timed out; retrying "
                f"({attempt}/{max_attempts}) in {delay_seconds}s…[/yellow]"
            )
            log_event(
                "MODEL_READ_TIMEOUT_RETRY",
                {"attempt": attempt, "delay_seconds": delay_seconds},
            )
            await asyncio.sleep(delay_seconds)

    if full and full.content:
        log_event("LLM_CONTENT", full.content)
        await runtime.events.emit("agent.message", {"content": full.content})

    return {
        "messages": [full],
        "tool_calls": full.tool_calls if full.tool_calls else []
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
    from src.agent.tools import tools_by_name
    from src.runtime.services import get_runtime

    # Async because MCP tools are coroutine-only StructuredTools; ainvoke also
    # covers the sync native tools by running them in an executor.
    tool_responses = []
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
            return str(result)
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
        await runtime.events.emit(
            "tool.started", {"tool": tool_call["name"], "args": tool_call.get("args", {}), "prefix": prefix}
        )
        log_event(
            "TOOL_CALL",
            {
                "tool": tool_call["name"],
                "args": tool_call.get("args", {}),
            },
        )

        if tool_call["name"] not in tools_by_name:
            result = (
                f"Error: no such tool '{tool_call['name']}'. Available"
                f" tools: {', '.join(sorted(tools_by_name))}"
            )
            log_event("TOOL_ERROR", result)
            await runtime.events.emit(
                "tool.failed", {"tool": tool_call["name"], "args": tool_call.get("args", {}), "error": result, "prefix": prefix}
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
                # Direct execution without gate checks
                result = await tool.ainvoke(tool_call["args"])
                if tool_call["name"] == "playwright_browser_navigate":
                    record_application_destination(tool_call["args"].get("url"))
                    destination = re.search(r"Page URL:\s*(https?://[^\s)]+)", str(result))
                    if destination:
                        record_application_destination(destination.group(1))
                auto_simplify_result = (
                    pre_auto_simplify_result
                    or await auto_simplify_if_new_form(tool_call["name"])
                )
                if auto_simplify_result:
                    result = f"{result}\n\n{auto_simplify_result}"
                log_event("TOOL_RESULT", str(result))
                await runtime.events.emit(
                    "tool.completed",
                    {
                        "tool": tool_call["name"],
                        "args": tool_call.get("args", {}),
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
                    {"tool": tool_call["name"], "args": tool_call.get("args", {}), "error": str(e), "prefix": prefix},
                )

        tool_responses.append(
            ToolMessage(content=str(result), tool_call_id=tool_call["id"])
        )
        await runtime.controller.set_tool(None)

    return {"messages": tool_responses}










    
