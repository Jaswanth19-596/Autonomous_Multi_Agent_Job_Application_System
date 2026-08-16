from pathlib import Path

import pytest

import src.automation.simplify_selenium as simplify_selenium
from src.automation.simplify_selenium import (
    SimplifyBrowserError,
    SimplifyChromeConfig,
    _click_simplify_autofill_control,
    _click_simplify_autofill_skills_button,
    _click_simplify_select_all_skills,
    _click_simplify_skills_dropdown,
    _focus_or_open_application_tab,
    _simplify_skills_autofill_status,
    _trigger_simplify_command,
    _validate_config,
    default_chrome_automation_user_data_dir,
    trigger_simplify_all_skills_autofill,
)


def test_uses_non_default_macos_automation_directory(monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: Path("/Users/tester"))

    assert default_chrome_automation_user_data_dir("Darwin") == (
        "/Users/tester/Library/Application Support/Google/Chrome-Automation"
    )


def test_requires_simplify_in_the_selected_profile(tmp_path):
    config = SimplifyChromeConfig(
        user_data_dir=tmp_path,
        profile_directory="Default",
        extension_id="simplify-id",
    )

    with pytest.raises(SimplifyBrowserError, match="not installed"):
        _validate_config(config, "https://jobs.example.com/apply")


def test_dispatches_simplify_autofill_hotkey_through_chrome():
    class Driver:
        def __init__(self):
            self.commands = []

        def execute_cdp_cmd(self, command, params):
            self.commands.append((command, params))

    driver = Driver()
    _trigger_simplify_command(driver)

    assert [params["type"] for _, params in driver.commands] == ["keyDown", "keyUp"]
    assert all(command == "Input.dispatchKeyEvent" for command, _ in driver.commands)
    assert all(params["modifiers"] == 9 for _, params in driver.commands)


def test_clicks_injected_simplify_control_before_using_hotkey():
    class Driver:
        def __init__(self):
            self.script = None

        def execute_script(self, script):
            self.script = script
            return "Autofill This Page"

    driver = Driver()

    assert _click_simplify_autofill_control(driver) == "Autofill This Page"
    assert "#fill-button" in driver.script
    assert "shadowRoot" in driver.script


def test_accepts_all_known_simplify_action_labels_from_simplify_ui():
    class Driver:
        def execute_script(self, script):
            self.script = script
            return None

    driver = Driver()
    _click_simplify_autofill_control(driver)

    assert "autofill\\s+my\\s+application" in driver.script
    assert "auto(?:fill+|flll)\\s+this\\s+form" in driver.script
    assert "continue\\s+application" in driver.script
    assert "create\\s+account" in driver.script
    assert "sign\\s+in" in driver.script
    assert "simplifyOwned" in driver.script


def test_reuses_playwright_application_tab_when_selenium_attaches():
    class SwitchTo:
        def __init__(self, driver):
            self.driver = driver

        def window(self, handle):
            self.driver.current_url = self.driver.urls[handle]

    class Driver:
        window_handles = ["other", "application"]
        urls = {
            "other": "https://example.com/",
            "application": "https://jobs.example.com/apply/123",
        }
        current_url = ""
        get_calls = []

        def __init__(self):
            self.switch_to = SwitchTo(self)

        def get(self, url):
            self.get_calls.append(url)

    driver = Driver()
    _focus_or_open_application_tab(driver, "https://jobs.example.com/apply/123")

    assert driver.current_url == "https://jobs.example.com/apply/123"
    assert driver.get_calls == []


def test_skills_controls_use_simplify_specific_labels():
    class Driver:
        def __init__(self):
            self.scripts = []

        def execute_script(self, script):
            self.scripts.append(script)
            return 34 if "autofill\\s+(\\d+)\\s+skills?" in script else True

    driver = Driver()

    assert _click_simplify_skills_dropdown(driver)
    assert _click_simplify_select_all_skills(driver)
    assert _click_simplify_autofill_skills_button(driver) == 34
    assert "select skills to autofill" in driver.scripts[0].lower()
    assert "^select all$" in driver.scripts[1].lower()
    assert "autofill\\s+(\\d+)\\s+skills?" in driver.scripts[2]


def test_skills_status_reads_completion_and_panel_visibility():
    class Driver:
        def execute_script(self, script):
            self.script = script
            return {"complete": True, "selector_visible": False, "text": "Autofill complete"}

    driver = Driver()

    assert _simplify_skills_autofill_status(driver) == {
        "complete": True,
        "selector_visible": False,
        "text": "Autofill complete",
    }
    assert "autofill (?:is )?complete" in driver.script.lower()


def test_all_skills_workflow_waits_for_simplify_completion(monkeypatch, tmp_path):
    class Driver:
        current_url = "https://jobs.example.com/apply/123"

        def execute_script(self, script):
            assert script == "return document.readyState"
            return "complete"

    driver = Driver()
    config = SimplifyChromeConfig(
        user_data_dir=tmp_path,
        profile_directory="Default",
        extension_id="simplify-id",
        timeout_seconds=1,
    )
    calls = []

    monkeypatch.setattr(simplify_selenium, "_validate_config", lambda *_: None)
    monkeypatch.setattr(simplify_selenium, "ensure_chrome_automation", lambda *_: config)
    monkeypatch.setattr(simplify_selenium, "_attach_driver", lambda *_: driver)
    monkeypatch.setattr(simplify_selenium, "_focus_or_open_application_tab", lambda *_: None)
    monkeypatch.setattr(
        simplify_selenium,
        "_click_simplify_skills_dropdown",
        lambda _: calls.append("dropdown") or True,
    )
    monkeypatch.setattr(
        simplify_selenium,
        "_click_simplify_select_all_skills",
        lambda _: calls.append("select-all") or True,
    )
    monkeypatch.setattr(
        simplify_selenium,
        "_click_simplify_autofill_skills_button",
        lambda _: calls.append("autofill") or 34,
    )
    monkeypatch.setattr(
        simplify_selenium,
        "_simplify_skills_autofill_status",
        lambda _: calls.append("wait") or {"complete": True, "selector_visible": True},
    )

    result = trigger_simplify_all_skills_autofill(driver.current_url, config)

    assert calls == ["dropdown", "select-all", "autofill", "wait"]
    assert result.selected_count == 34
    assert result.completion == "complete"
