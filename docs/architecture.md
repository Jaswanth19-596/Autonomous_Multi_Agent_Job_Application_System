# Architecture

## Overview

**Jaswanth's Agent** is a **stateful, human-in-the-loop agent** built on LangGraph. The agent reads user intent, plans tool calls, and pauses for human approval before any execution. It is a terminal-based chatbot that interacts with the user through `prompt_toolkit` and renders output with `rich`.

## Graph Topology

```
                   ┌──────────────────┐
                   │  user_input_node │ ← user types a message
                   └────────┬─────────┘
                            ↓
          ┌─────────────────┴──────────────────┐
          │      execution_node                │  ← LLM thinks, may emit tool_calls
          └─────────────────┬──────────────────┘
                            ↓ (tool_calls?)
                     tool_calls │ no tool_calls
               ┌───────────────┴────────┐
               │                        ↓ (loop back)
        ┌──────┴───────┐        ┌──────────────┐
        │human_approval│        │user_input_node│
        │    _node     │        └──────────────┘
        └──────┬───────┘
               ↓ (approved?)
        denied │  approved
        ┌──────┴──────┐
        │ execution   │
        │    node     │
        └──────┬──────┘
               ↓
        ┌──────────────┐
        │  tool_node   │  ← dispatches each approved tool call
        └──────┬───────┘
               ↓
        ┌──────────────┐
        │execution_node│  (loop back for next turn)
        └──────────────┘
```

## State

```python
class State(MessagesState, total=False):
    approved: bool = False
    tool_calls: list[dict] = None
```

- **`messages`** — inherited from `MessagesState`, holds the full conversation
- **`approved`** — last human-approval decision (`True`/`False`)
- **`tool_calls`** — most recent tool calls proposed by the LLM

## Conditions (conditional edges)

| Condition | Route |
|-----------|-------|
| `execution_condition` | If `tool_calls` are present → `human_approval_node`, otherwise → `user_input_node` |
| `human_approval_condition` | If `approved` is `True` → `tool_node`, otherwise → `execution_node` |

## Nodes

| Node | Responsibility |
|------|----------------|
| `user_input_node` | Read a line from the user via `prompt_toolkit` (with in-memory history); append a `HumanMessage` |
| `execution_node` | Stream the LLM (with tools bound); show a "Thinking..." spinner and live Markdown output; capture `tool_calls` |
| `human_approval_node` | Pretty-print pending tool calls; ask `y/n`; emit a `HumanMessage` reflecting the decision |
| `tool_node` | Dispatch each approved tool call to its handler by name; append returned `ToolMessage`s |

## Tools

All tools are defined in `src/tools.py` and registered in `src/nodes.py` (both the `tools` list for binding and the `tools_by_name` dict for dispatch):

| Tool | Purpose |
|------|---------|
| **`terminal`** | Execute a shell command via LangChain's `ShellTool`; returns stdout (or stderr on failure) |
| **`web_search`** | Search the web for data via `TavilySearch` (max 5 results, general topic) |
| **`read_file`** | Read the contents of a file and return them as a string |
| **`update_file`** | Replace `old_string` with `new_string` in a file and print the diff via `rich` |

To add a new tool: decorate a function with `@tool` in `src/tools.py`, then register it in both the `tools` list and `tools_by_name` dict in `src/nodes.py`.

## Model & Providers

- **LLM** — `ChatOpenRouter` (`deepseek/deepseek-v4-flash-latest`) with an `OPENROUTER_API_KEY` from `.env`. The model is bound with all registered tools via `model.bind_tools(tools)`.
- **Web search** — `TavilySearch` using a `TAVILY_API_KEY` from `.env`.
- The system prompt instructs the agent to classify tasks as simple (execute directly) or complex (write a plan first) and to require human approval for dangerous operations.

## UI

- `src/ui.py` renders a welcome panel (`Jaswanth's Agent`) on startup using `rich`.
- The conversation is driven by `prompt_toolkit` for input and `rich` (`Live`, `Markdown`, `Spinner`) for streaming output.

## Safety

- Every tool call passes through `human_approval_node` — no tool runs without explicit `y`/`yes`.
- The `terminal` tool captures output instead of streaming it, preventing accidental pager/tty hijacks.
- `.env` is git-ignored; secrets (API keys) never enter the repo.
