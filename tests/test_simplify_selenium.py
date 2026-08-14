from pathlib import Path

import pytest

from src.simplify_selenium import (
    SimplifyBrowserError,
    SimplifyChromeConfig,
    _click_simplify_autofill_control,
    _focus_or_open_application_tab,
    _trigger_simplify_command,
    _validate_config,
    default_chrome_automation_user_data_dir,
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
