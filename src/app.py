from langgraph.graph import StateGraph, START, END, MessagesState
from typing import TypedDict, Any
# pyrefly: ignore [missing-import]
from src.nodes import execution_node, tool_node, human_approval_node, user_input_node
from langchain_core.messages import SystemMessage, HumanMessage
from src.ui import show_welcome
from rich.console import Console
import asyncio
from pypdf import PdfReader
from pydantic import Field
from src.tools import terminal, web_search, update_file, read_file, get_pending_jobs, update_job_status, delegate_job_application, tools_by_name, worker_model_holder
from langchain_openrouter import ChatOpenRouter
import os
from mcp_client.mcp_manager import MCPManager

mcp_manager = MCPManager("mcp_client/servers.json")

manager_tools = [delegate_job_application, get_pending_jobs, update_job_status]
worker_tools = [web_search, update_file, read_file]


async def shutdown():

    await mcp_manager.close()

model = ChatOpenRouter(
    # model = "~deepseek/deepseek-v4-flash-latest",
    model = "openai/gpt-5.6-luna",
    api_key = os.environ["OPENROUTER_API_KEY"]
)

manager_model = model.bind_tools(manager_tools)
worker_model = model.bind_tools(worker_tools)


async def initialize_tools():
    """Wires up native + MCP tools. Returns {server_name: error} for servers that failed."""
    global worker_model, worker_tools
    errors = await mcp_manager.connect()
    mcp_tools = await mcp_manager.get_langchain_tools()
    worker_tools = [web_search, update_file, read_file] + mcp_tools
    worker_model = model.bind_tools(worker_tools)
    worker_model_holder["model"] = worker_model

    print("worker_tools : ", len(worker_tools))

    tools = manager_tools + worker_tools
    tools_by_name.clear()
    tools_by_name.update({tool.name : tool for tool in tools})
    return errors


console = Console()

class ManagerState(MessagesState, total = False):
    subagents: list = Field(description="List of subagents")
    tool_calls: list[dict] = None
    model: Any = None

class WorkerState(MessagesState, total = False):
    approved: bool = False
    tool_calls: list[dict] = None
    model: Any = None


def execution_condition(state):
    if state['tool_calls']:
        return "human_approval_node"
    return "user_input_node"

def human_approval_condition(state):
    if state["approved"] == True:
        return "tool_node"
    else:
        return "execution_node"

def build_manager_graph():

    graph = StateGraph(ManagerState)

    graph.add_node(user_input_node)
    graph.add_node(execution_node)
    graph.add_node(tool_node)
    graph.add_node(human_approval_node) 

    graph.add_edge(START, "user_input_node")
    graph.add_edge("user_input_node", "execution_node")
    graph.add_conditional_edges(
        "execution_node",
        execution_condition,
        {"human_approval_node": "human_approval_node", "user_input_node": "user_input_node"},
    )
    graph.add_conditional_edges(
        "human_approval_node",
        human_approval_condition,
        {"execution_node": "execution_node", "tool_node": "tool_node"},
    )
    graph.add_edge("tool_node", "execution_node")


    return graph.compile()

def worker_execution_condition(state):
    if state.get("tool_calls"):
        return "human_approval_node"
    return END


def build_worker_graph():
    graph = StateGraph(WorkerState)

    graph.add_node(execution_node)
    graph.add_node(human_approval_node)
    graph.add_node(tool_node)
 
    graph.add_edge(START, "execution_node")
    graph.add_conditional_edges(
        "execution_node",
        worker_execution_condition,
        {"human_approval_node": "human_approval_node", END: END},
    )
    graph.add_conditional_edges(
        "human_approval_node",
        human_approval_condition,
        {"execution_node": "execution_node", "tool_node": "tool_node"},
    )
    graph.add_edge("tool_node", "execution_node")
 
    return graph.compile()
 
 
with open('prompts/manager_systemprompt.md', 'r') as f:
    MANAGER_SYSTEM_PROMPT = f.read()

with open('prompts/worker_systemprompt.md', 'r') as f:
    WORKER_SYSTEM_PROMPT = f.read()

with open("user_details/qna.md", "r") as f:
    qna = f.read()

reader = PdfReader("user_details/resume.pdf")
resume = "\n".join(page.extract_text() or "" for page in reader.pages)


user_profile = "Here is the User's profile : Resume - " + resume + "\n\nQuestions & Answers - " + qna

 

graph = build_manager_graph()


async def main():

    show_welcome()

    with console.status("[cyan]Connecting to tools (MCP servers)...[/cyan]"):
        errors = await initialize_tools()

    for name, error in errors.items():
        console.print(f"[yellow]Warning: MCP server '{name}' unavailable, continuing without it.[/yellow]")
        console.print(f"[dim]  {error}[/dim]")

    try:
        await graph.ainvoke(
            {
                "messages": [SystemMessage(content = MANAGER_SYSTEM_PROMPT)],
                "model": manager_model
            },
            config={"recursion_limit": 200}
        )

    finally:
        await shutdown()



if __name__ == "__main__":
    import sys
    # Ensure 'from src.app import ...' reuses this module instead of
    # re-importing src/app.py as a second module instance.
    sys.modules.setdefault("src.app", sys.modules[__name__])
    asyncio.run(main())