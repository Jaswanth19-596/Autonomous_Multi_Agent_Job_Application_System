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


@dataclass(frozen=True)
class SimplifySkillsAutofillResult:
    """Outcome of Simplify's select-all-skills autofill workflow."""

    url: str
    selected_count: int | None
    completion: str
    elapsed_seconds: float


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
    action button into supported applications. Its label differs by Simplify
    version, so recognize the supported action labels while avoiding similarly
    named controls rendered by the underlying ATS page.
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
        const simplifyHost = element => element && element.matches(
          '[class*="simplify" i], [id*="simplify" i], [data-testid*="simplify" i], [data-simplify-extension], [data-simplify-overlay]'
        );
        const simplifyElement = element => element && (
          simplifyHost(element) || Boolean(element.closest(
            '[class*="simplify" i], [id*="simplify" i], [data-testid*="simplify" i], [data-simplify-extension], [data-simplify-overlay]'
          ))
        );
        const visit = (root, simplifyOwned = false) => {
          if (!root || seen.has(root)) return;
          seen.add(root);
          const owned = simplifyOwned || simplifyHost(root.host);
          roots.push({root, simplifyOwned: owned});
          for (const node of root.querySelectorAll('*')) {
            if (node.shadowRoot) visit(node.shadowRoot, owned || simplifyHost(node));
          }
        };
        visit(document);

        const candidates = [];
        const actionScore = label => {
          if (/autofill\s+this\s+page/i.test(label)) return 90;
          if (/autofill\s+my\s+application/i.test(label)) return 80;
          if (/auto(?:fill+|flll)\s+this\s+form/i.test(label)) return 70;
          if (/run\s+autofill\s+again/i.test(label)) return 60;
          if (/(?:^|\s)autofill(?:\s|$)/i.test(label)) return 50;
          if (/continue\s+application/i.test(label)) return 40;
          if (/create\s+account/i.test(label)) return 30;
          if (/sign\s+in/i.test(label)) return 20;
          return 0;
        };
        for (const {root, simplifyOwned} of roots) {
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
            const score = element.id === 'fill-button' ? 100 : actionScore(label);
            // Labels such as "Sign in" are generic on ATS pages. Accept them
            // only from Simplify's shadow tree; #fill-button is a trusted
            // extension-specific identifier even when rendered in light DOM.
            if (score && (element.id === 'fill-button' || simplifyOwned || simplifyElement(element))) {
              candidates.push({element, label, score});
            }
          }
        }
        candidates.sort((a, b) => b.score - a.score);
        const selected = candidates[0];
        if (!selected) return null;
        selected.element.click();
        return selected.label || 'Simplify Autofill';
        """
    )


def _click_simplify_skills_dropdown(driver: Any) -> bool:
    """Open Simplify's ``Select skills to autofill`` menu, if present.

    Simplify renders the panel in nested open shadow roots.  The selector is
    deliberately label-based: Workday has no equivalent control, so this
    cannot accidentally operate on a native Workday field.
    """
    return bool(
        driver.execute_script(
            r"""
            const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
            const visible = element => {
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

            for (const root of roots) {
              for (const element of root.querySelectorAll(
                'button, [role="button"], input, [role="combobox"]'
              )) {
                const text = clean([
                  element.getAttribute('aria-label'), element.getAttribute('placeholder'),
                  element.innerText, element.textContent, element.getAttribute('title')
                ].filter(Boolean).join(' '));
                if (visible(element) && !element.disabled &&
                    /^select skills to autofill(?:\s|$)/i.test(text)) {
                  element.click();
                  return true;
                }
              }
            }
            return false;
            """
        )
    )


def _click_simplify_select_all_skills(driver: Any) -> bool:
    """Select the explicit ``Select all`` entry in Simplify's skills menu."""
    return bool(
        driver.execute_script(
            r"""
            const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
            const visible = element => {
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

            for (const root of roots) {
              for (const element of root.querySelectorAll(
                'button, [role="button"], [role="option"], li, a, div'
              )) {
                const text = clean([
                  element.getAttribute('aria-label'), element.innerText, element.textContent
                ].filter(Boolean).join(' '));
                if (visible(element) && !element.disabled && /^select all$/i.test(text)) {
                  element.click();
                  return true;
                }
              }
            }
            return false;
            """
        )
    )


def _click_simplify_autofill_skills_button(driver: Any) -> int | None:
    """Click Simplify's all-skills confirmation button and return its count."""
    result = driver.execute_script(
        r"""
        const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
        const visible = element => {
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
          for (const element of root.querySelectorAll('button, [role="button"], a')) {
            const text = clean([
              element.getAttribute('aria-label'), element.innerText, element.textContent,
              element.getAttribute('title')
            ].filter(Boolean).join(' '));
            const match = text.match(/^autofill\s+(\d+)\s+skills?$/i);
            if (visible(element) && !element.disabled && match) {
              candidates.push({ element, count: Number(match[1]) });
            }
          }
        }
        if (!candidates.length) return null;
        candidates.sort((a, b) => b.count - a.count);
        candidates[0].element.click();
        return candidates[0].count;
        """
    )
    return int(result) if result is not None else None


def _simplify_skills_autofill_status(driver: Any) -> dict[str, bool | str]:
    """Read only completion signals from the Simplify skills panel."""
    return driver.execute_script(
        r"""
        const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
        const visible = element => {
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

        const text = roots.map(root => clean(root.innerText || root.textContent))
          .filter(Boolean).join(' ').slice(0, 4000);
        const selectorVisible = roots.some(root => Array.from(root.querySelectorAll(
          'button, [role="button"], input, [role="combobox"]'
        )).some(element => {
          const label = clean([
            element.getAttribute('aria-label'), element.getAttribute('placeholder'),
            element.innerText, element.textContent
          ].filter(Boolean).join(' '));
          return visible(element) && /^select skills to autofill(?:\s|$)/i.test(label);
        }));
        return {
          complete: /autofill (?:is )?complete|skills? (?:were |have been )?autofilled/i.test(text),
          selector_visible: selectorVisible,
          text
        };
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


def trigger_simplify_all_skills_autofill(
    application_url: str,
    config: SimplifyChromeConfig | None = None,
) -> SimplifySkillsAutofillResult:
    """Ask Simplify to autofill every skill it found for the active Workday job.

    This is intentionally a separate action from the ordinary page autofill.
    It is safe to call only after the worker has observed Simplify's visible
    ``Select skills to autofill`` prompt.  After confirming all skills, the
    extension can take several minutes, so this function owns the wait rather
    than letting the worker issue browser actions against a changing page.
    """
    config = config or SimplifyChromeConfig.from_environment()
    _validate_config(config, application_url)
    ensure_chrome_automation(config)
    driver = _attach_driver(config)
    start = time.monotonic()
    ui_deadline = start + config.timeout_seconds
    completion_timeout = float(os.environ.get("SIMPLIFY_SKILLS_TIMEOUT_SECONDS", "360"))
    completion_deadline = start + max(1.0, completion_timeout)

    def wait_for(action: Any, description: str) -> Any:
        while time.monotonic() < ui_deadline:
            result = action(driver)
            if result:
                return result
            time.sleep(0.25)
        raise SimplifyBrowserError(f"Simplify's {description} was not visible in time.")

    try:
        _focus_or_open_application_tab(driver, application_url)
        while driver.execute_script("return document.readyState") != "complete":
            if time.monotonic() >= ui_deadline:
                raise SimplifyBrowserError("The application page did not finish loading in time.")
            time.sleep(0.2)

        wait_for(_click_simplify_skills_dropdown, "Select skills to autofill menu")
        wait_for(_click_simplify_select_all_skills, "Select all skills option")
        selected_count = wait_for(
            _click_simplify_autofill_skills_button,
            "Autofill Skills confirmation button",
        )

        missing_selector_checks = 0
        while time.monotonic() < completion_deadline:
            status = _simplify_skills_autofill_status(driver)
            if bool(status.get("complete")):
                return SimplifySkillsAutofillResult(
                    url=driver.current_url,
                    selected_count=selected_count,
                    completion="complete",
                    elapsed_seconds=time.monotonic() - start,
                )

            # Simplify versions that close the skills panel on success do not
            # expose completion text. Require repeated observations to avoid
            # treating a short re-render as completion.
            if not bool(status.get("selector_visible")):
                missing_selector_checks += 1
                if missing_selector_checks >= 3:
                    return SimplifySkillsAutofillResult(
                        url=driver.current_url,
                        selected_count=selected_count,
                        completion="panel_closed",
                        elapsed_seconds=time.monotonic() - start,
                    )
            else:
                missing_selector_checks = 0
            time.sleep(1)

        raise SimplifyBrowserError(
            "Simplify started autofilling all skills but did not report completion within "
            f"{int(completion_timeout)} seconds. Inspect the Simplify panel before continuing."
        )
    except Exception:
        # This session is shared with Playwright MCP; never quit it here.
        raise
