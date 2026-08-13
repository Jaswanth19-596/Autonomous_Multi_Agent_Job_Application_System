import json

from src.simplify_gate import (
    PAGE_FINGERPRINT_CODE,
    SIMPLIFY_SIDE_PANEL_AUTOFILL_CODE,
    authorize_simplify,
    has_simplify_authorization,
    is_gate_exempt_click,
    is_simplify_authorized,
    is_simplify_unsupported,
    mark_simplify_unsupported,
    parse_playwright_json,
    reset_simplify_authorization,
    simplify_result_authorizes_repairs,
)


def test_authorization_is_scoped_to_exact_page_fingerprint():
    reset_simplify_authorization()
    authorize_simplify("page-one", "clicked Autofill")

    assert is_simplify_authorized("page-one")
    assert not is_simplify_authorized("page-two")


def test_reset_revokes_authorization():
    authorize_simplify("page-one", "clicked Autofill")
    reset_simplify_authorization()

    assert not is_simplify_authorized("page-one")
    assert not has_simplify_authorization()


def test_parse_plain_playwright_json():
    payload = {"fingerprint": "abc", "status": "success", "clicked": True}

    assert parse_playwright_json(json.dumps(payload)) == payload


def test_parse_mcp_quoted_json_result():
    payload = {"fingerprint": "abc", "application_form": True}
    output = "### Result\n" + json.dumps(json.dumps(payload)) + "\n### Ran Playwright code"

    assert parse_playwright_json(output) == payload


def test_parse_mcp_semantic_result_without_fingerprint():
    payload = {
        "results": [
            {
                "field": "Mobile phone number",
                "status": "filled_and_verified",
            }
        ]
    }
    output = (
        "### Result\n"
        + json.dumps(json.dumps(payload))
        + "\n### Ran Playwright code\n```js\n({ results: [] })\n```"
    )

    assert parse_playwright_json(output) == payload


def test_parse_prefers_result_section_over_echoed_javascript_object():
    payload = {"ready_to_continue": True, "missing_required": []}
    output = (
        "### Result\n"
        + json.dumps(json.dumps(payload))
        + "\n### Ran Playwright code\n```js\n({ misleading: true })\n```"
    )

    assert parse_playwright_json(output) == payload


def test_privacy_acknowledgement_click_is_gate_exempt():
    assert is_gate_exempt_click(
        {"element": "Acknowledge data protection notice button"}
    )


def test_form_and_submit_clicks_are_not_gate_exempt():
    assert not is_gate_exempt_click({"element": "Country dropdown"})
    assert not is_gate_exempt_click({"element": "Apply button"})


def test_navigation_choice_is_not_misclassified_as_application_form():
    assert "apply manually" not in PAGE_FINGERPRINT_CODE.lower()


def test_page_fingerprint_is_strictly_url_scoped():
    assert "const fingerprintParts = { url: location.href };" in PAGE_FINGERPRINT_CODE
    assert "const fingerprintParts = { url: location.href };" in SIMPLIFY_SIDE_PANEL_AUTOFILL_CODE
    assert "headings:" not in PAGE_FINGERPRINT_CODE
    assert "progress:" not in PAGE_FINGERPRINT_CODE
    assert "controls:" not in PAGE_FINGERPRINT_CODE
    assert "dialogs:" not in PAGE_FINGERPRINT_CODE


def test_page_fingerprint_does_not_depend_on_rerendered_element_ids():
    unstable_identity = "el.id || el.name || String(index)"
    assert unstable_identity not in PAGE_FINGERPRINT_CODE
    assert unstable_identity not in SIMPLIFY_SIDE_PANEL_AUTOFILL_CODE


def test_simplify_and_gate_use_identical_url_fingerprinting():
    fingerprint = "const fingerprintParts = { url: location.href };"
    assert fingerprint in PAGE_FINGERPRINT_CODE
    assert fingerprint in SIMPLIFY_SIDE_PANEL_AUTOFILL_CODE


def test_simplify_tool_prioritizes_exact_side_panel_action():
    assert "autofill\\s+this\\s+page" in SIMPLIFY_SIDE_PANEL_AUTOFILL_CODE
    assert "run\\s+autofill\\s+again" in SIMPLIFY_SIDE_PANEL_AUTOFILL_CODE
    assert "bExact - aExact" in SIMPLIFY_SIDE_PANEL_AUTOFILL_CODE


def test_changed_fields_authorize_repairs():
    assert simplify_result_authorizes_repairs(
        {"clicked": True, "changed_fields": 7, "simplify_text": ""}
    )


def test_explicit_autofill_complete_authorizes_repeated_attempt():
    assert simplify_result_authorizes_repairs(
        {
            "clicked": True,
            "changed_fields": 0,
            "simplify_text": "Autofill complete! 8 fields need review",
        }
    )


def test_already_complete_authorizes_without_clicking_again():
    assert simplify_result_authorizes_repairs(
        {
            "clicked": False,
            "already_complete": True,
            "changed_fields": 0,
            "simplify_text": "Autofill complete! 8 fields need review",
        }
    )


def test_click_without_changes_or_completion_does_not_authorize():
    assert not simplify_result_authorizes_repairs(
        {"clicked": True, "changed_fields": 0, "simplify_text": "Autofill"}
    )


def test_manual_fallback_uses_same_page_scoped_authorization():
    reset_simplify_authorization()
    authorize_simplify("linkedin-easy-apply-step", "Manual fallback: unavailable")

    assert is_simplify_authorized("linkedin-easy-apply-step")
    assert not is_simplify_authorized("linkedin-easy-apply-next-step")


def test_absent_panel_is_remembered_for_same_origin_only():
    reset_simplify_authorization()
    first_step = json.dumps({"url": "https://jobs.example.com/apply/one"})
    next_step = json.dumps({"url": "https://jobs.example.com/apply/two"})
    different_ats = json.dumps({"url": "https://other.example.com/apply"})

    mark_simplify_unsupported(first_step)

    assert is_simplify_unsupported(next_step)
    assert not is_simplify_unsupported(different_ats)


def test_reset_clears_unsupported_origin_state():
    fingerprint = json.dumps({"url": "https://jobs.example.com/apply"})
    mark_simplify_unsupported(fingerprint)
    reset_simplify_authorization()

    assert not is_simplify_unsupported(fingerprint)


def test_page_reset_preserves_unsupported_origin_state():
    fingerprint = json.dumps({"url": "https://jobs.example.com/apply"})
    mark_simplify_unsupported(fingerprint)
    reset_simplify_authorization(clear_unsupported=False)

    assert is_simplify_unsupported(fingerprint)
    reset_simplify_authorization()
