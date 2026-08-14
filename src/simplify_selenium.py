"""Attach Selenium to the Chrome session shared with Playwright MCP."""

from __future__ import annotations

import os
import platform
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen


class SimplifyBrowserError(RuntimeError):
    """Raised when the profile-backed Simplify browser cannot be used."""


@dataclass(frozen=True)
class SimplifyChromeConfig:
    user_data_dir: Path
    profile_directory: str
    extension_id: str
    chrome_binary: str | None = None
    timeout_seconds: float = 15.0
    debugging_port: int = 9222

    @classmethod
    def from_environment(cls) -> "SimplifyChromeConfig":
        user_data_dir = Path(os.environ.get(
            "CHROME_AUTOMATION_USER_DATA_DIR",
            default_chrome_automation_user_data_dir(),
        )).expanduser()
        profile_directory = os.environ.get("CHROME_PROFILE_DIRECTORY", "Default").strip()
        extension_id = os.environ.get("SIMPLIFY_EXTENSION_ID", "").strip()
        chrome_binary = os.environ.get("CHROME_BINARY", "").strip() or default_chrome_binary()
        timeout_seconds = float(os.environ.get("SIMPLIFY_TIMEOUT_SECONDS", "15"))
        debugging_port = int(os.environ.get("CHROME_DEBUGGING_PORT", "9222"))
        return cls(
            user_data_dir=user_data_dir,
            profile_directory=profile_directory,
            extension_id=extension_id,
            chrome_binary=chrome_binary,
            timeout_seconds=timeout_seconds,
            debugging_port=debugging_port,
        )

    @property
    def cdp_endpoint(self) -> str:
        return f"http://127.0.0.1:{self.debugging_port}"


@dataclass(frozen=True)
class SimplifyAutofillResult:
    url: str
    filled_before: int
    filled_after: int
    control: str

    @property
    def changed_fields(self) -> int:
        return max(0, self.filled_after - self.filled_before)


def default_chrome_automation_user_data_dir(system: str | None = None) -> str:
    """Return a non-default profile suitable for local CDP automation."""
    system = system or platform.system()
    if system == "Darwin":
        return str(Path.home() / "Library/Application Support/Google/Chrome-Automation")
    if system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            raise SimplifyBrowserError(
                "LOCALAPPDATA is not set; configure CHROME_AUTOMATION_USER_DATA_DIR."
            )
        return str(Path(local_app_data) / "Google/Chrome-Automation/User Data")
    return str(Path.home() / ".config/google-chrome-automation")


def default_chrome_binary(system: str | None = None) -> str | None:
    """Return Chrome's usual executable path when it is known."""
    system = system or platform.system()
    if system == "Darwin":
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if system == "Windows":
        program_files = os.environ.get("PROGRAMFILES")
        return str(Path(program_files) / "Google/Chrome/Application/chrome.exe") if program_files else None
    return None


def _validate_config(config: SimplifyChromeConfig, application_url: str) -> None:
    parsed_url = urlparse(application_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise SimplifyBrowserError("The active application URL must be an http(s) URL.")
    if not config.extension_id:
        raise SimplifyBrowserError("SIMPLIFY_EXTENSION_ID is not configured.")
    if any(part in {"", ".", ".."} for part in Path(config.profile_directory).parts):
        raise SimplifyBrowserError("CHROME_PROFILE_DIRECTORY must name a Chrome profile, such as Default.")
    extension_dir = (
        config.user_data_dir
        / config.profile_directory
        / "Extensions"
        / config.extension_id
    )
    if not extension_dir.is_dir():
        raise SimplifyBrowserError(
            "Simplify is not installed in the configured Chrome profile "
            f"({extension_dir})."
        )


def _filled_control_count(driver: Any) -> int:
    return int(
        driver.execute_script(
            """
            return Array.from(document.querySelectorAll('input, textarea, select'))
              .filter((control) => {
                if (control.type === 'hidden' || control.type === 'file' ||
                    control.type === 'submit' || control.type === 'button' ||
                    control.type === 'reset') return false;
                if (control.type === 'checkbox' || control.type === 'radio') return control.checked;
                return Boolean(String(control.value || '').trim());
              }).length;
            """
        )
    )


def _trigger_simplify_command(driver: Any) -> None:
    """Send Simplify's built-in Alt+Shift+F command through Chrome DevTools.

    Simplify 3.x exposes this command as ``trigger-autofill``. Dispatching it
    at the browser level is more reliable than trying to locate the Chrome
    toolbar, which Selenium intentionally does not expose as page DOM.
    """
    modifiers = 1 | 8  # Alt | Shift in the Chrome DevTools protocol.
    common = {
        "key": "F",
        "code": "KeyF",
        "windowsVirtualKeyCode": 70,
        "nativeVirtualKeyCode": 70,
        "modifiers": modifiers,
    }
    driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyDown", **common})
    driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyUp", **common})


def _click_simplify_autofill_control(driver: Any) -> str | None:
    """Click Simplify's real page control, traversing its open shadow roots.

    Chrome DevTools keyboard events are delivered to the renderer and cannot be
    relied on to invoke a Chrome extension command. Simplify already injects an
    ``Autofill This Page`` button into supported applications, so click that
    control directly instead.
    """
    return driver.execute_script(
        r"""
        const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
        const isVisible = element => {
          const style = getComputedStyle(element);
          const rect = element.getBoundingClientRect();
          return style.display !== 'none' && style.visibility !== 'hidden'
            && Number(style.opacity) !== 0 && rect.width > 0 && rect.height > 0;
        };
        const roots = [];
        const seen = new Set();
        const visit = root => {
          if (!root || seen.has(root)) return;
          seen.add(root);
          roots.push(root);
          for (const node of root.querySelectorAll('*')) {
            if (node.shadowRoot) visit(node.shadowRoot);
          }
        };
        visit(document);

        const candidates = [];
        for (const root of roots) {
          for (const element of root.querySelectorAll(
            '#fill-button, button, [role="button"], a'
          )) {
            const label = clean([
              element.getAttribute('aria-label'),
              element.innerText,
              element.textContent,
              element.getAttribute('title')
            ].filter(Boolean).join(' '));
            if (!isVisible(element) || element.disabled ||
                element.getAttribute('aria-disabled') === 'true') continue;
            const exact = element.id === 'fill-button' ||
              /autofill\s+(this\s+page|my\s+application)/i.test(label);
            if (exact) candidates.push({element, label});
          }
        }
        candidates.sort((a, b) => {
          const score = candidate => candidate.element.id === 'fill-button' ? 2
            : /autofill\s+this\s+page/i.test(candidate.label) ? 1 : 0;
          return score(b) - score(a);
        });
        const selected = candidates[0];
        if (!selected) return null;
        selected.element.click();
        return selected.label || 'Simplify Autofill';
        """
    )


def _cdp_is_available(config: SimplifyChromeConfig) -> bool:
    try:
        with urlopen(f"{config.cdp_endpoint}/json/version", timeout=1) as response:
            return response.status == 200
    except OSError:
        return False


def ensure_chrome_automation(config: SimplifyChromeConfig | None = None) -> SimplifyChromeConfig:
    """Start the one local Chrome instance both automation clients share."""
    config = config or SimplifyChromeConfig.from_environment()
    if _cdp_is_available(config):
        return config
    if not config.chrome_binary or not Path(config.chrome_binary).is_file():
        raise SimplifyBrowserError(
            "Google Chrome was not found. Set CHROME_BINARY to its executable path."
        )

    config.user_data_dir.mkdir(parents=True, exist_ok=True)
    command = [
        config.chrome_binary,
        f"--remote-debugging-port={config.debugging_port}",
        f"--user-data-dir={config.user_data_dir}",
        f"--profile-directory={config.profile_directory}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    try:
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        raise SimplifyBrowserError(f"Could not start Chrome: {exc}") from exc

    deadline = time.monotonic() + config.timeout_seconds
    while time.monotonic() < deadline:
        if _cdp_is_available(config):
            return config
        time.sleep(0.2)
    raise SimplifyBrowserError(
        f"Chrome started but did not expose CDP at {config.cdp_endpoint}."
    )


def _attach_driver(config: SimplifyChromeConfig) -> Any:
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError as exc:  # Keeps non-browser commands usable before sync.
        raise SimplifyBrowserError(
            "Selenium dependencies are missing. Run `uv sync` to install them."
        ) from exc

    options = Options()
    options.debugger_address = f"127.0.0.1:{config.debugging_port}"

    try:
        return webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=options
        )
    except Exception as exc:
        raise SimplifyBrowserError(
            "Could not attach Selenium to the shared Chrome CDP session. "
            "Original error: " + str(exc)
        ) from exc


def _focus_or_open_application_tab(driver: Any, application_url: str) -> None:
    """Reuse Playwright's application tab instead of navigating a second tab."""
    for handle in driver.window_handles:
        driver.switch_to.window(handle)
        if driver.current_url == application_url:
            return
    driver.get(application_url)


def trigger_simplify_autofill(
    application_url: str,
    config: SimplifyChromeConfig | None = None,
) -> SimplifyAutofillResult:
    """Trigger Simplify in the exact Chrome tab controlled by Playwright MCP."""
    config = config or SimplifyChromeConfig.from_environment()
    _validate_config(config, application_url)
    ensure_chrome_automation(config)
    driver = _attach_driver(config)
    try:
        _focus_or_open_application_tab(driver, application_url)
        deadline = time.monotonic() + config.timeout_seconds
        while driver.execute_script("return document.readyState") != "complete":
            if time.monotonic() >= deadline:
                raise SimplifyBrowserError("The application page did not finish loading in time.")
            time.sleep(0.2)

        filled_before = _filled_control_count(driver)
        control = _click_simplify_autofill_control(driver)
        if not control:
            # Keep the extension command as a fallback for versions that show
            # their panel only after the command has been invoked.
            _trigger_simplify_command(driver)
            time.sleep(1)
            control = _click_simplify_autofill_control(driver)
        if not control:
            raise SimplifyBrowserError(
                "Simplify is installed but its Autofill This Page control was not visible."
            )

        filled_after = filled_before
        while time.monotonic() < deadline:
            time.sleep(0.5)
            filled_after = _filled_control_count(driver)
            if filled_after > filled_before:
                break
        return SimplifyAutofillResult(
            url=driver.current_url,
            filled_before=filled_before,
            filled_after=filled_after,
            control=control,
        )
    except Exception:
        # This session is shared with Playwright MCP; never quit it here.
        raise
