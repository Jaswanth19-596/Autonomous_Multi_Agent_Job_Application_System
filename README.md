# FilePilot

An AI-powered file organization agent built with **LangGraph** and **LangChain**.

FilePilot is an agentic system that interprets natural-language commands, plans terminal operations, and requests human approval before executing potentially destructive actions on the filesystem.

## Features

- 🧠 **LLM-driven planning** via OpenRouter (`minimax/minimax-m3`)
- 🛡️ **Human-in-the-loop approval** for every tool call
- 💬 **Interactive REPL** with input history (powered by `prompt_toolkit`)
- 🎨 **Rich terminal UI** with welcome panel
- 🔧 **Extensible tool registry** — add new tools in `src/tools.py`

## Project Structure

```
langgraph/
├── src/              # Application source
│   ├── agent/        # Graph definition, nodes, and LLM-facing tools
│   ├── application/  # Application workflow, metrics, and form semantics
│   ├── automation/   # Browser and Simplify integrations
│   ├── cli/          # Terminal commands and UI
│   ├── core/         # Configuration and logging
│   ├── data/         # Workbook and candidate-profile helpers
│   └── jobs/         # Job discovery services
├── mcp_client/       # MCP adapters for external services
├── tests/            # Unit & smoke tests
├── docs/             # Design & architecture docs
├── scripts/          # Utility scripts
├── pyproject.toml    # Project metadata & dependencies (uv)
└── uv.lock           # Pinned dependency lockfile
```

## Setup

Requires **Python 3.11+** and [uv](https://docs.astral.sh/uv/).

```bash
# Install dependencies
uv sync

# Set up environment variables
echo "OPENROUTER_API_KEY=your_key_here" > .env
```

### Simplify Chrome extension

The app starts one Chrome instance with a local Chrome DevTools Protocol (CDP)
endpoint. Selenium and Playwright MCP attach to it, so Simplify and the worker
operate on the same tab. Add these values (the defaults match macOS):

```bash
SIMPLIFY_EXTENSION_ID=pbanhockgagggenencehbnadejlgchfc
CHROME_AUTOMATION_USER_DATA_DIR="$HOME/Library/Application Support/Google/Chrome-Automation"
CHROME_PROFILE_DIRECTORY=Default
CHROME_DEBUGGING_PORT=9222
```

Run `uv sync` after pulling these changes. On the first run, install Simplify
and sign in within the Chrome-Automation window. Keep the CDP endpoint local;
it grants full control of the browser profile. The worker and Selenium then
operate on the exact same Chrome tab.

## Usage

```bash
uv run python -m src.agent.app
```

You will see a welcome banner, then a `>` prompt. Type natural-language commands; the agent will propose terminal commands and ask for your approval before running them.

### Example
```
> list the files in my current directory
The agent wants to perform the following actions:
0. terminal : ls -la
Do you approve the above operation : (y/n) y
```

## Architecture

The graph is defined in `src/agent/app.py` as a `StateGraph` with the following nodes:

```
START → user_input_node → execution_node
                              ↓ (if tool calls)
                       human_approval_node
                              ↓ (if approved)
                          tool_node → execution_node (loop)
```

See `docs/architecture.md` for the full design.

## Development

```bash
# Run tests
uv run pytest

# Lint / format (TODO)
```

## License

This project is licensed under the [MIT License](LICENSE).
