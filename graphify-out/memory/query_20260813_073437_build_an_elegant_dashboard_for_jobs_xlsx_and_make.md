---
type: "query"
date: "2026-08-13T07:34:37.386012+00:00"
question: "Build an elegant dashboard for jobs.xlsx and make the applications table searchable and scrollable."
contributor: "graphify"
source_nodes: ["save_jobs_to_excel()", "update_job_status()", "get_jobs()", "tools.py"]
---

# Q: Build an elegant dashboard for jobs.xlsx and make the applications table searchable and scrollable.

## Answer

Expanded from graph vocabulary: [excel, jobs, application, status, jobboard, runtime, tools]. Added a Dashboard sheet with formula-driven pipeline and efficiency KPIs, reordered Applications so operational fields precede raw scrape data, retained the ID and status headers used by get_jobs and update_job_status, and changed workbook mutations to preserve dashboard sheets.

## Source Nodes

- save_jobs_to_excel()
- update_job_status()
- get_jobs()
- tools.py