import asyncio
import json

from src.application.dropdown_selection import build_select_dropdown_option_code


def test_dropdown_program_opens_before_resolving_and_clicking_options():
    code = build_select_dropdown_option_code("work_authorization", "Yes")

    opened = code.index("steps.push('clicked_control')")
    waited = code.index("const waitForOptions")
    selected = code.index("await exact.locator.click")

    assert opened < waited < selected
    assert "interaction_steps" in code
    assert "options_rendered" in code
    assert "norm(candidate.label) === wanted" in code
    assert "available_options" in code
    assert "option_not_found" in code
    assert "norm(candidate.label).includes(wanted)" not in code


def test_dropdown_program_supports_portalled_and_workday_options():
    code = build_select_dropdown_option_code("question-id", "Yes")

    assert '[role="listbox"]:visible' in code
    assert '[role="menu"]:visible' in code
    assert 'data-automation-id="promptOption"' in code
    assert "data-agent-dropdown-preexisting" in code
    assert "getByText(request.option, {exact: true})" in code


def test_dropdown_tool_reports_exact_choices_when_option_is_missing(monkeypatch):
    from src.agent.tools import select_dropdown_option

    async def fake_call_tool(*_args, **_kwargs):
        return json.dumps({
            "status": "unresolved",
            "failure_code": "option_not_found",
            "field": "Work authorization",
            "requested_option": "Yes",
            "available_options": ["Yes for all", "Yes for some", "No"],
        })

    monkeypatch.setattr("src.agent.app.mcp_manager.call_tool", fake_call_tool)

    response = asyncio.run(select_dropdown_option.ainvoke({
        "field": "work_authorization", "option": "Yes",
    }))

    assert response.startswith("DROPDOWN_OPTION_NOT_FOUND")
    assert "'Yes for all'" in response
    assert "'Yes for some'" in response
    assert "do not shorten or approximate" in response


def test_dropdown_tool_confirms_the_selected_exact_option(monkeypatch):
    from src.agent.tools import select_dropdown_option

    calls = []

    async def fake_call_tool(*args, **kwargs):
        calls.append((args, kwargs))
        return json.dumps({
            "status": "selected",
            "field": "Work authorization",
            "selected_option": "Yes for all",
            "interaction_steps": [
                "clicked_control", "options_rendered", "selected_option",
            ],
        })

    monkeypatch.setattr("src.agent.app.mcp_manager.call_tool", fake_call_tool)

    response = asyncio.run(select_dropdown_option.ainvoke({
        "field": "work_authorization", "option": "Yes for all",
    }))

    assert response == "DROPDOWN_SELECTION_SUCCESS: Selected exact option 'Yes for all' for 'Work authorization'."
    assert len(calls) == 1
    assert calls[0][0][0:2] == ("playwright", "browser_run_code_unsafe")
    assert "clicked_control" in calls[0][0][2]["code"]
