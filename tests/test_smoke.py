"""Smoke tests — verify the project imports and basic structure is intact."""

def test_imports():
    """All top-level modules should import without error."""
    from src.agent import app, nodes, tools
    from src.cli import ui
    assert app is not None
    assert nodes is not None
    assert tools is not None
    assert ui is not None


def test_terminal_tool_runs():
    """The terminal tool should execute simple commands."""
    from src.agent.tools import terminal
    result = terminal.invoke({"command": "echo hello"})
    assert "hello" in result


def test_welcome_runs():
    """show_welcome() should execute without raising."""
    from src.cli.ui import show_welcome
    # Just ensure the function is callable; we don't assert on its output
    assert callable(show_welcome)


def test_graph_compiles():
    """The LangGraph graph in app.py should compile successfully."""
    from src.agent.app import graph
    assert graph is not None


def test_update_job_status(tmp_path, monkeypatch):
    """update_job_status tool should update application status in jobs.xlsx."""
    import pandas as pd
    from src.agent.tools import update_job_status

    test_excel = tmp_path / "jobs.xlsx"
    df = pd.DataFrame([
        {"id": "101", "title": "Dev", "application_status": "Not Applied"},
        {"id": "102", "title": "QA", "application_status": "Not Applied"},
    ])
    df.to_excel(test_excel, index=False)

    monkeypatch.setattr("src.agent.tools._EXCEL_PATH", test_excel)

    res = update_job_status.invoke({"job_id": "101", "status": "Applied"})
    assert "Successfully updated" in res

    updated_df = pd.read_excel(test_excel, dtype=str)
    row_101 = updated_df[updated_df["id"] == "101"].iloc[0]
    row_102 = updated_df[updated_df["id"] == "102"].iloc[0]

    assert row_101["application_status"] == "Applied"
    assert row_102["application_status"] == "Not Applied"


def test_get_jobs_by_id_streams_one_row_without_pandas_queue_read(tmp_path, monkeypatch):
    """Known job IDs should not build the complete jobs queue first."""
    import pandas as pd
    from src.agent.tools import get_jobs

    test_excel = tmp_path / "jobs.xlsx"
    pd.DataFrame([
        {"id": "101", "title": "Dev", "application_status": "Not Applied"},
        {"id": "102", "title": "QA", "application_status": "Applied"},
    ]).to_excel(test_excel, index=False)

    monkeypatch.setattr("src.agent.tools._EXCEL_PATH", test_excel)

    def unexpected_queue_read(*args, **kwargs):
        raise AssertionError("ID lookup should not call pandas.read_excel")

    monkeypatch.setattr("src.agent.tools.pd.read_excel", unexpected_queue_read)

    result = get_jobs.invoke({"job_id": "102"})

    assert result == {"id": "102", "title": "QA", "application_status": "Applied"}


def test_get_jobs_treats_an_empty_optional_id_as_a_queue_request(tmp_path, monkeypatch):
    import pandas as pd
    from src.agent.tools import get_jobs

    test_excel = tmp_path / "jobs.xlsx"
    pd.DataFrame([
        {"id": "101", "title": "Dev", "application_status": "Not Applied"},
        {"id": "102", "title": "QA", "application_status": "Applied"},
    ]).to_excel(test_excel, index=False)
    monkeypatch.setattr("src.agent.tools._EXCEL_PATH", test_excel)

    result = get_jobs.invoke({"filters": ["Not Applied"], "n": 1, "job_id": ""})

    assert result == [{"id": "101", "title": "Dev", "application_status": "Not Applied"}]
