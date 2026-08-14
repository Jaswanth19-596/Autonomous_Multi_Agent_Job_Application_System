"""Detect new application form steps and scope automatic Simplify attempts."""

from __future__ import annotations

import base64
import json
import re
import threading


FORM_SIGNATURE_CODE = r"""
async (page) => {
  const payload = await page.evaluate(() => {
    const visible = element => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden'
        && Number(style.opacity) !== 0 && rect.width > 0 && rect.height > 0;
    };
    const controls = Array.from(document.querySelectorAll('input, textarea, select'))
      .filter(element => {
        if (!visible(element) || element.disabled || element.type === 'hidden') return false;
        return !element.closest(
          '[data-simplify-extension], [data-simplify-overlay], [class*="simplify" i], [id*="simplify" i]'
        );
      })
      .map(element => [
        element.tagName,
        element.type || '',
        element.id || '',
        element.name || '',
        element.getAttribute('aria-label') || ''
      ].join(':'));
    return { url: location.href, controls };
  });
  if (payload.controls.length < 3) return 'SIMPLIFY_FORM_ABSENT';
  const encoded = btoa(unescape(encodeURIComponent(JSON.stringify({
    signature: JSON.stringify(payload),
    control_count: payload.controls.length
  }))));
  return 'SIMPLIFY_FORM_READY:' + encoded;
}
"""

_attempted_signatures: set[str] = set()
_lock = threading.RLock()


def reset_auto_simplify_attempts() -> None:
    """Reset the per-job cache before a worker starts a new application."""
    with _lock:
        _attempted_signatures.clear()


def form_signature_from_playwright_output(output: str) -> tuple[str, int] | None:
    """Extract the compact form fingerprint returned by ``FORM_SIGNATURE_CODE``."""
    match = re.search(r"SIMPLIFY_FORM_READY:([A-Za-z0-9+/=]+)", output)
    if not match:
        return None
    try:
        payload = json.loads(base64.b64decode(match.group(1)).decode("utf-8"))
        signature = payload["signature"]
        control_count = int(payload["control_count"])
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Could not decode the current application form signature") from exc
    return signature, control_count


def claim_auto_simplify_attempt(signature: str) -> bool:
    """Return true once for each distinct visible form step in the current job."""
    with _lock:
        if signature in _attempted_signatures:
            return False
        _attempted_signatures.add(signature)
        return True
