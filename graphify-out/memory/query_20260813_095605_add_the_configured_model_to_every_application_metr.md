---
type: "query"
date: "2026-08-13T09:56:05.804156+00:00"
question: "Add the configured model to every application metric row so costs can be compared by model."
contributor: "graphify"
source_nodes: ["app.py", "tools.py", "delegate_job_application()"]
---

# Q: Add the configured model to every application metric row so costs can be compared by model.

## Answer

Expanded from graph vocabulary: [application, model, jobboard, cost, tools]. The worker model is named once in app.py, passed into the metrics session at delegation, and written to the model column beside jobboard. Each row can now be filtered or grouped by model with application_cost_usd, duration, and tool calls.

## Source Nodes

- app.py
- tools.py
- delegate_job_application()