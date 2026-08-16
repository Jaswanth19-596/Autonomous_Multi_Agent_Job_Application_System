"""Runtime enforcement for the Simplify-first application workflow."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class SimplifyAuthorization:
    page_fingerprint: str
    evidence: str


_authorization: SimplifyAuthorization | None = None
_unsupported_origins: set[str] = set()
_authorization_lock = threading.RLock()


def reset_simplify_authorization(*, clear_unsupported: bool = True) -> None:
    global _authorization
    with _authorization_lock:
        _authorization = None
        if clear_unsupported:
            _unsupported_origins.clear()


def fingerprint_origin(page_fingerprint: str) -> str:
    """Return the web origin embedded in a page fingerprint."""
    try:
        url = json.loads(page_fingerprint).get("url", "")
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    except (json.JSONDecodeError, TypeError, AttributeError):
        return ""


def mark_simplify_unsupported(page_fingerprint: str) -> None:
    """Remember that Simplify did not inject its panel on this ATS origin."""
    origin = fingerprint_origin(page_fingerprint)
    if origin:
        with _authorization_lock:
            _unsupported_origins.add(origin)


def is_simplify_unsupported(page_fingerprint: str) -> bool:
    origin = fingerprint_origin(page_fingerprint)
    with _authorization_lock:
        return bool(origin and origin in _unsupported_origins)


def authorize_simplify(page_fingerprint: str, evidence: str) -> None:
    global _authorization
    with _authorization_lock:
        _authorization = SimplifyAuthorization(page_fingerprint, evidence)


def is_simplify_authorized(page_fingerprint: str) -> bool:
    with _authorization_lock:
        return bool(
            _authorization
            and _authorization.page_fingerprint == page_fingerprint
        )


def has_simplify_authorization() -> bool:
    """Return whether the current worker has any live Simplify authorization.

    This is used only while Chrome's native file chooser is open. During that
    modal state Playwright cannot execute JavaScript to recompute a page
    fingerprint, and the chooser can only have been opened by an already
    guarded click on the authorized application page.
    """
    with _authorization_lock:
        return _authorization is not None


def simplify_result_authorizes_repairs(result: dict) -> bool:
    """Accept changed fields or Simplify's own explicit completion evidence."""
    if not result.get("clicked") and not result.get("already_complete"):
        return False
    if int(result.get("changed_fields", 0) or 0) > 0:
        return True
    simplify_text = str(result.get("simplify_text", "")).lower()
    return "autofill complete" in simplify_text


def parse_playwright_json(output: str) -> dict:
    """Extract any JSON object returned by Playwright MCP's run-code tool.

    Despite living in the Simplify gate, this parser is shared by all semantic
    browser tools.  Their payloads intentionally do not contain a
    ``fingerprint`` key, so requiring one here turns successful browser actions
    into false tool failures.
    """
    def decode_object(candidate: str) -> dict | None:
        try:
            value = json.loads(candidate)
            # Playwright normally JSON-quotes a JavaScript string result.
            if isinstance(value, str):
                value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None
        return value if isinstance(value, dict) else None

    # Prefer the explicit result section. This avoids accidentally parsing an
    # object literal from the echoed JavaScript program below it.
    result_section = output
    if "### Result" in output:
        result_section = output.split("### Result", 1)[1].split("### Ran", 1)[0]

    # MCP commonly renders the JavaScript string result as a JSON-quoted line:
    # `"{\"fingerprint\": ...}"`. Decode those lines before scanning the
    # surrounding human-readable Playwright report.
    for line in result_section.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        value = decode_object(candidate)
        if value is not None:
            return value

    decoder = json.JSONDecoder()
    for index, char in enumerate(result_section):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(result_section[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    excerpt = " ".join(output.strip().split())[:300]
    raise ValueError(
        "Playwright did not return the expected JSON object"
        + (f": {excerpt}" if excerpt else "")
    )


PAGE_FINGERPRINT_CODE = r"""
async (page) => {
  return await page.evaluate(() => {
  // Authorization is intentionally URL-scoped. Nothing rendered within the
  // same URL (validation, progress, headings, modals, or controls) constitutes
  // a new Simplify step.
  const fingerprintParts = { url: location.href };
  const requiredControls = Array.from(document.querySelectorAll(
    'input[required], select[required], textarea[required], [aria-required="true"]'
  )).filter(el => {
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.visibility !== 'hidden' && style.display !== 'none' && rect.width && rect.height;
  });
  return JSON.stringify({
    fingerprint: JSON.stringify(fingerprintParts),
    application_form: requiredControls.length > 0
  });
  });
}
"""


SIMPLIFY_SIDE_PANEL_AUTOFILL_CODE = r"""
async (page) => {
  const result = await page.evaluate(async () => {
  const visible = (el) => {
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.visibility !== 'hidden' && style.display !== 'none' && rect.width && rect.height;
  };
  const label = (el) => [
    el.innerText,
    el.textContent,
    el.getAttribute('aria-label'),
    el.getAttribute('title'),
    el.getAttribute('data-testid')
  ].filter(Boolean).join(' ').trim().replace(/\s+/g, ' ');

  const fingerprintParts = { url: location.href };
  const fingerprint = JSON.stringify(fingerprintParts);

  // Search only roots owned by Simplify. Searching the whole document can
  // confuse an ATS-native "Autofill with Resume" button with the extension.
  const hosts = Array.from(document.querySelectorAll(
    '[class*="simplify" i], [id*="simplify" i], [data-testid*="simplify" i]'
  ));
  const roots = [];
  const visit = (root) => {
    if (!root || roots.includes(root)) return;
    roots.push(root);
    for (const node of root.querySelectorAll('*')) {
      if (node.shadowRoot) visit(node.shadowRoot);
    }
  };
  const refreshRoots = () => {
    for (const host of hosts) if (host.shadowRoot) visit(host.shadowRoot);
  };
  refreshRoots();

  if (!hosts.length) {
    return {
      fingerprint,
      status: 'unavailable',
      simplify_present: false,
      reason: 'Simplify did not inject a host element into this page'
    };
  }
  if (!roots.length) {
    return {
      fingerprint,
      status: 'unavailable',
      simplify_present: false,
      reason: 'Simplify host exists but exposes no open shadow root'
    };
  }

  const simplifyText = () => roots
    .map(root => (root.innerText || root.textContent || '').trim().replace(/\s+/g, ' '))
    .filter(Boolean)
    .join(' | ')
    .slice(0, 1000);
  const currentSimplifyText = simplifyText();
  if (/autofill complete/i.test(currentSimplifyText)) {
    return {
      fingerprint,
      status: 'success',
      clicked: false,
      already_complete: true,
      changed_fields: 0,
      simplify_text: currentSimplifyText,
      control: 'Autofill complete'
    };
  }

  const actionScore = (text) => {
    if (/autofill\s+this\s+page/i.test(text)) return 90;
    if (/autofill\s+my\s+application/i.test(text)) return 80;
    if (/auto(?:fill+|flll)\s+this\s+form/i.test(text)) return 70;
    if (/run\s+autofill\s+again/i.test(text)) return 60;
    if (/(?:^|\s)autofill(?:\s|$)/i.test(text)) return 50;
    if (/continue\s+application/i.test(text)) return 40;
    if (/create\s+account/i.test(text)) return 30;
    if (/sign\s+in/i.test(text)) return 20;
    return 0;
  };
  const findAutofill = () => {
    const candidates = [];
    for (const root of roots) {
      for (const element of root.querySelectorAll('button, [role="button"], a')) {
        const text = label(element);
        const score = actionScore(text);
        if (visible(element) && score) {
          candidates.push({ element, text, score });
        }
      }
    }
    return candidates;
  };
  let candidates = findAutofill();
  if (!candidates.length) {
    // Simplify may initially expose only a collapsed launcher.
    const launchers = [];
    for (const root of roots) {
      for (const element of root.querySelectorAll('button, [role="button"], a')) {
        const text = label(element);
        if (visible(element) && /simplify/i.test(text)) launchers.push(element);
      }
    }
    if (launchers.length) {
      launchers[0].click();
      await new Promise(resolve => setTimeout(resolve, 1000));
      refreshRoots();
      candidates = findAutofill();
    }
  }
  if (!candidates.length) {
    return {
      fingerprint,
      status: 'unavailable',
      simplify_present: true,
      reason: 'Simplify is active, but no accessible Autofill control was found'
    };
  }

  candidates.sort((a, b) => b.score - a.score);
  const selected = candidates[0];
  const fieldState = () => Array.from(document.querySelectorAll('input, textarea, select'))
    .filter(el => el.type !== 'hidden')
    .map((el, index) => ({
      key: el.id || el.name || el.getAttribute('aria-label') || `${el.tagName}:${index}`,
      value: el.type === 'checkbox' || el.type === 'radio'
        ? String(el.checked)
        : String(el.value || '')
    }));
  const beforeFields = fieldState();
  selected.element.click();

  return {
    fingerprint,
    status: 'success',
    clicked: true,
    control: selected.text,
    simplify_hosts: hosts.length,
    before_fields: beforeFields
  };
  });

  // Allow Simplify's content script to populate the form and settle.
  if (result.status === 'success') {
    await page.waitForTimeout(8000);
    const verification = await page.evaluate(() => {
      const visible = (el) => {
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.visibility !== 'hidden' && style.display !== 'none' && rect.width && rect.height;
      };
      const fields = Array.from(document.querySelectorAll('input, textarea, select'))
        .filter(el => el.type !== 'hidden')
        .map((el, index) => ({
          key: el.id || el.name || el.getAttribute('aria-label') || `${el.tagName}:${index}`,
          value: el.type === 'checkbox' || el.type === 'radio'
            ? String(el.checked)
            : String(el.value || '')
        }));
      const requiredEmpty = Array.from(document.querySelectorAll(
        'input[required], textarea[required], select[required], [aria-required="true"]'
      )).filter(el => visible(el) && (
        (el.type === 'checkbox' || el.type === 'radio') ? !el.checked : !String(el.value || '').trim()
      )).length;

      const simplifyText = [];
      const visit = (root) => {
        for (const node of root.querySelectorAll('*')) {
          if (node.shadowRoot) visit(node.shadowRoot);
        }
        const text = (root.innerText || root.textContent || '').trim().replace(/\s+/g, ' ');
        if (text) simplifyText.push(text);
      };
      for (const host of document.querySelectorAll(
        '[class*="simplify" i], [id*="simplify" i], [data-testid*="simplify" i]'
      )) {
        if (host.shadowRoot) visit(host.shadowRoot);
      }
      return {
        fields,
        required_empty: requiredEmpty,
        simplify_text: simplifyText.join(' | ').slice(0, 600)
      };
    });

    const before = new Map(result.before_fields.map(field => [field.key, field.value]));
    result.changed_fields = verification.fields.filter(
      field => before.has(field.key) && before.get(field.key) !== field.value
    ).length;
    result.required_empty = verification.required_empty;
    result.simplify_text = verification.simplify_text;
    delete result.before_fields;

    if (result.changed_fields === 0 && result.required_empty > 0) {
      result.status = 'no_effect';
      result.reason = 'Simplify Autofill was clicked but did not change any form fields';
    }
  }
  return JSON.stringify(result);
}
"""


def is_gate_exempt_click(args: dict) -> bool:
    """Allow controls that only dismiss blockers and do not fill/submit forms."""
    label = str(args.get("element", "")).strip().lower()
    exempt_phrases = (
        "acknowledge",
        "accept cookies",
        "accept all cookies",
        "close privacy",
        "close data privacy",
        "close cookie",
    )
    return any(phrase in label for phrase in exempt_phrases)
