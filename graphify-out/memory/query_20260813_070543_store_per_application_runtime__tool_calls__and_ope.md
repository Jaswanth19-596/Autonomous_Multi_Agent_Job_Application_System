---
type: "query"
date: "2026-08-13T07:05:43.179931+00:00"
question: "Store per-application runtime, tool calls, and OpenRouter cost in jobs.xlsx instead of a separate file."
contributor: "graphify"
source_nodes: ["update_job_status()", "tools.py", "job_fetcher.py", "Tool Node"]
---

# Q: Store per-application runtime, tool calls, and OpenRouter cost in jobs.xlsx instead of a separate file.

## Answer

Expanded from graph vocabulary: [excel, job, application, runtime, tool, calls, status]. The matching job row is the stable persistence point. Worker-boundary snapshots capture OpenRouter cumulative key usage before and after the application; their delta is stored as application_cost_usd, while tool dispatch increments the per-job counter.

## Source Nodes

- update_job_status()
- tools.py
- job_fetcher.py
- Tool Node