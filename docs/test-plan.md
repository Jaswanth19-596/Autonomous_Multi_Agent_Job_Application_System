# Test Update Plan

## Problem
Current smoke tests (`tests/test_smoke.py`) fail:
- `test_imports` and `test_graph_compiles` -> `EOFError` because importing
  `src.app` runs `show_welcome()` + `graph.invoke(...)` at module load time
  (triggers a live LLM call and an interactive prompt).
- Tests don't cover the new modules/tools added in the refactor
  (`read_file`, `update_file`, `web_search`, `tool_node`, graph topology).

## Changes

### 1. Source (make it testable) — `src/app.py`
- Move the startup behavior (`show_welcome()`, `graph.invoke(...)`) into a
  `main()` function.
- Guard it with `if __name__ == "__main__":`.
- Extract a `build_graph()` function so tests can build a fresh, isolated graph.
- Keep a module-level `graph = build_graph()` (import is now side-effect free).

### 2. Tests — update `tests/test_smoke.py`
- Keep import test (now safe after app.py fix).
- Graph test: replace blind `graph is not None` with structural checks
  (nodes registered, edges + conditional edge routing logic).
- Add unit tests for `tool_node` dispatch with mocked tool calls.
- Add tests for `read_file` and `update_file` tools on a temp file.
- Keep `terminal` and welcome tests (already passing).

## Acceptance
- `uv run pytest` passes without needing a live API key or interactive input.
