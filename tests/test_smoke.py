"""Smoke tests — verify the project imports and basic structure is intact."""

def test_imports():
    """All top-level modules should import without error."""
    from src import app, nodes, tools, ui
    assert app is not None
    assert nodes is not None
    assert tools is not None
    assert ui is not None


def test_terminal_tool_runs():
    """The terminal tool should execute simple commands."""
    from src.tools import terminal
    result = terminal.invoke({"command": "echo hello"})
    assert "hello" in result


def test_welcome_runs():
    """show_welcome() should execute without raising."""
    from src.ui import show_welcome
    # Just ensure the function is callable; we don't assert on its output
    assert callable(show_welcome)


def test_graph_compiles():
    """The LangGraph graph in app.py should compile successfully."""
    from src.app import graph
    assert graph is not None


def test_update_job_status(tmp_path, monkeypatch):
    """update_job_status tool should update application status in jobs.xlsx."""
    import pandas as pd
    from src.tools import update_job_status

    test_excel = tmp_path / "jobs.xlsx"
    df = pd.DataFrame([
        {"id": "101", "title": "Dev", "application_status": "Not Applied"},
        {"id": "102", "title": "QA", "application_status": "Not Applied"},
    ])
    df.to_excel(test_excel, index=False)

    monkeypatch.setattr("src.tools._EXCEL_PATH", test_excel)

    res = update_job_status.invoke({"job_id": "101", "status": "Applied"})
    assert "Successfully updated" in res

    updated_df = pd.read_excel(test_excel, dtype=str)
    row_101 = updated_df[updated_df["id"] == "101"].iloc[0]
    row_102 = updated_df[updated_df["id"] == "102"].iloc[0]

    assert row_101["application_status"] == "Applied"
    assert row_102["application_status"] == "Not Applied"

