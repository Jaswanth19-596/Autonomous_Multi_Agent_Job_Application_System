import base64
import json

from src.automation.simplify_auto import (
    FORM_SIGNATURE_CODE,
    claim_auto_simplify_attempt,
    form_signature_from_playwright_output,
    reset_auto_simplify_attempts,
)
from src.agent.nodes import _is_transient_read_timeout


def test_signature_code_detects_non_simplify_form_controls():
    assert "payload.controls.length < 3" in FORM_SIGNATURE_CODE
    assert "data-simplify-overlay" in FORM_SIGNATURE_CODE


def test_form_signature_is_decoded_from_playwright_result():
    payload = {"signature": '{"url":"https://jobs.example.com/apply"}', "control_count": 8}
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()

    assert form_signature_from_playwright_output(
        f'### Result\n"SIMPLIFY_FORM_READY:{encoded}"'
    ) == (payload["signature"], 8)


def test_auto_simplify_attempt_is_limited_to_one_attempt_per_form_step():
    reset_auto_simplify_attempts()

    assert claim_auto_simplify_attempt("form-one")
    assert not claim_auto_simplify_attempt("form-one")
    assert claim_auto_simplify_attempt("form-two")


def test_read_timeout_is_retryable_but_other_errors_are_not():
    assert _is_transient_read_timeout(RuntimeError("The read operation timed out"))
    assert not _is_transient_read_timeout(RuntimeError("invalid selector"))
