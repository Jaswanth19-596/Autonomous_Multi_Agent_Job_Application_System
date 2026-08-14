import os
from dotenv import load_dotenv
from langchain_core.messages import ToolMessage, HumanMessage, AIMessage, SystemMessage
from prompt_toolkit.history import InMemoryHistory
from src.commands import (
    build_session,
    prompt_for_input,
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




def user_input_node(state):
    # Interactive REPL with pop-up autocomplete, styling & history
    session = build_session(history)
    message = prompt_for_input(session)

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


def execution_node(state, config=None):
    full = None
    model = state.get("model")
    if model is None and config and "configurable" in config:
        model = config["configurable"].get("model")

    if model is None:
        from src.app import manager_model
        model = manager_model

    from src.logger import get_job_prefix, log_event

    # pruned_msgs, num_pruned = _prune_messages(state["messages"])
    pruned_msgs, num_pruned = state["messages"], 0
    if num_pruned > 0:
        prefix = get_job_prefix()
        console.print(f"{prefix}[dim cyan]⚡ Context optimized: pruned {num_pruned} old DOM payload(s)[/dim cyan]")
        log_event("TOKEN_OPT", f"Pruned {num_pruned} old DOM payload(s) from context window")

    with Live(console=console, refresh_per_second=10) as live:
        live.update(Spinner("dots", text=f"{get_job_prefix()}[bold cyan]Thinking...[/bold cyan]"))
        for chunk in model.stream(pruned_msgs):
            full = chunk if full is None else full + chunk
            if chunk.content:
                live.update(Markdown(full.content))

    if full and full.content:
        log_event("LLM_CONTENT", full.content)

    return {
        "messages": [full],
        "tool_calls": full.tool_calls if full.tool_calls else []
    }


def format_tool_call(i, tool_call):
    from src.logger import redact_sensitive
    name = tool_call.get("name", "unknown_tool")
    args = redact_sensitive(tool_call.get("args", {}))
    return f"[bold cyan]{i}. {name}[/bold cyan]\n[dim]   Args:[/dim] {args}"


def human_approval_node(state):

    dangerous_calls = [
        tc for tc in state["tool_calls"] if tc["name"] in DANGEROUS_TOOLS
    ]

    # If none of the pending tool calls are dangerous, auto-approve.
    if not dangerous_calls:
        return {"approved": True}

    # Only show the dangerous tool calls that need approval.
    console.print("\n[bold red]⚠️  The agent wants to perform the following dangerous action(s):[/bold red]\n")

    for i, tool_call in enumerate(dangerous_calls):
        console.print(format_tool_call(i, tool_call))

    message = input("\nDo you approve the above operation : (y/n) ").strip().lower()

    if message in ('y', 'yes'):
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
    from src.app import mcp_manager
    from src.logger import get_job_prefix, log_event, redact_sensitive
    from src.tools import tools_by_name

    # Async because MCP tools are coroutine-only StructuredTools; ainvoke also
    # covers the sync native tools by running them in an executor.
    tool_responses = []
    prefix = get_job_prefix()

    for tool_call in state["tool_calls"]:
        console.print(
            f"\n{prefix}[bold yellow]🛠️  Executing Tool:[/bold yellow] [bold"
            f" cyan]{tool_call['name']}[/bold cyan]"
        )
        if tool_call.get("args"):
            console.print(
                f"[dim]   Args:[/dim] {redact_sensitive(tool_call['args'])}"
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
            console.print(
                f"{prefix}[bold red]❌ No such tool"
                f" '{tool_call['name']}'[/bold red]"
            )
            log_event("TOOL_ERROR", result)
        else:
            tool = tools_by_name[tool_call["name"]]
            try:
                # Direct execution without gate checks
                result = await tool.ainvoke(tool_call["args"])
                log_event("TOOL_RESULT", str(result))
            except Exception as e:
                # Report the failure back to the model instead of killing the session.
                console.print(
                    f"{prefix}[red]Tool '{tool_call['name']}' failed: {e}[/red]"
                )
                result = f"Error: tool '{tool_call['name']}' failed: {e}"
                log_event("TOOL_ERROR", str(e))

        tool_responses.append(
            ToolMessage(content=str(result), tool_call_id=tool_call["id"])
        )

    return {"messages": tool_responses}










    
