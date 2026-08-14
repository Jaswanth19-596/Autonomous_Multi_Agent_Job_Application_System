---
type: "query"
date: "2026-08-13T09:36:34.463466+00:00"
question: "Record the actual job board after LinkedIn redirects to the employer's ATS."
contributor: "graphify"
source_nodes: ["delegate_job_application()", "tools.py", "Application Page Schema"]
---

# Q: Record the actual job board after LinkedIn redirects to the employer's ATS.

## Answer

Expanded from graph vocabulary: [application, jobboard, url, tools]. Metrics now capture the browser's final URL after the worker completes, prefer it over a checkpoint URL, persist it as application_url, and derive jobboard from that ATS hostname. LinkedIn is treated as a source only and never saved as the ATS label.

## Source Nodes

- delegate_job_application()
- tools.py
- Application Page Schema