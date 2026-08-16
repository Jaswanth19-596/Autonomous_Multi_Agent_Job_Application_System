from __future__ import annotations

import pandas as pd


JOB_HTML = """
<html>
  <head>
    <title>Ignored title</title>
    <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "identifier": {"@type": "PropertyValue", "value": "greenhouse-123"},
        "title": "Platform Engineer",
        "hiringOrganization": {"@type": "Organization", "name": "Acme, Inc."},
        "description": "<p>Build reliable systems.</p>",
        "datePosted": "2026-08-15",
        "employmentType": "FULL_TIME",
        "jobLocation": {"@type": "Place", "address": {"addressLocality": "Austin", "addressRegion": "TX", "addressCountry": "US"}}
      }
    </script>
  </head>
  <body>Build reliable systems.</body>
</html>
"""


def test_fetch_job_profile_normalizes_json_ld_and_final_url(monkeypatch):
    from src.jobs import profile as job_profile

    monkeypatch.setattr(
        job_profile,
        "_load_page",
        lambda url, timeout_ms: (
            "https://boards.greenhouse.io/acme/jobs/123",
            "Platform Engineer at Acme, Inc.",
            JOB_HTML,
            "Build reliable systems.",
        ),
    )

    result = job_profile.fetch_job_profile("https://example.com/job")

    assert result["id"] == "greenhouse-123"
    assert result["link"] == "https://boards.greenhouse.io/acme/jobs/123"
    assert result["applyUrl"] == result["link"]
    assert result["title"] == "Platform Engineer"
    assert result["companyName"] == "Acme, Inc."
    assert result["location"] == "Austin, TX, US"
    assert result["descriptionText"] == "Build reliable systems."
    assert result["application_status"] == "Not Applied"


def test_url_profile_tool_upserts_and_preserves_existing_status(tmp_path, monkeypatch):
    from src.agent.tools import (
        get_job_profile_from_url,
        insert_job_profile_to_excel,
        update_job_status,
    )
    from src.jobs import profile as job_profile

    workbook = tmp_path / "jobs.xlsx"
    pd.DataFrame(columns=["id", "title", "companyName", "link", "applyUrl", "application_status"]).to_excel(
        workbook, index=False
    )
    monkeypatch.setattr("src.agent.tools._EXCEL_PATH", workbook)
    monkeypatch.setattr(
        job_profile,
        "_load_page",
        lambda url, timeout_ms: (url, "Platform Engineer at Acme, Inc.", JOB_HTML, "Build reliable systems."),
    )

    profile = get_job_profile_from_url.invoke({"link": "https://jobs.example.com/opening/123"})
    assert "error" not in profile
    assert "Successfully inserted" in insert_job_profile_to_excel.invoke({"job_profile": profile})

    assert "Successfully updated" in update_job_status.invoke(
        {"job_id": profile["id"], "status": "Applied"}
    )
    refreshed_profile = {**profile, "title": "Senior Platform Engineer"}
    assert "Successfully updated" in insert_job_profile_to_excel.invoke({"job_profile": refreshed_profile})

    jobs = pd.read_excel(workbook, dtype=str)
    assert len(jobs) == 1
    assert jobs.iloc[0]["title"] == "Senior Platform Engineer"
    assert jobs.iloc[0]["application_status"] == "Applied"


def test_fetch_job_profile_rejects_non_http_urls():
    from src.jobs.profile import fetch_job_profile

    try:
        fetch_job_profile("file:///tmp/job.html")
    except ValueError as exc:
        assert "http(s)" in str(exc)
    else:
        raise AssertionError("A non-http URL must be rejected")
