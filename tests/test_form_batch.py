import json

from src.application.form_batch import CLICK_NEXT_CONTROL_CODE, FORM_INSPECTION_CODE, build_batch_repair_code


def test_inspection_collects_all_controls_and_combobox_options_in_one_loop():
    assert "for (let index = 0; index < controls.length; index++)" in FORM_INSPECTION_CODE
    assert "document.querySelectorAll('[role=\"option\"]')" in FORM_INSPECTION_CODE
    assert "item.options" in FORM_INSPECTION_CODE


def test_batch_repair_embeds_plan_as_json_not_javascript_source():
    repairs = [{"key": "lastName", "value": "Mada"}]
    code = build_batch_repair_code(json.dumps(repairs))

    assert '"lastName"' in code
    assert "REPAIRS_JSON" not in code
    assert "for (const repair of repairs)" in code


def test_batch_repair_supports_native_and_custom_controls():
    code = build_batch_repair_code("[]")

    assert "tag === 'select'" in code
    assert "actualType === 'combobox'" in code
    assert "kind === 'checkbox' || kind === 'radio'" in code
    assert "status: 'unresolved'" in code


def test_batch_uses_playwright_native_operations_and_verifies_values():
    code = build_batch_repair_code("[]")

    assert "await control.fill" in code
    assert "await control.check" in code
    assert "await control.selectOption" in code
    assert "filled_and_verified" in code
    assert "value was not accepted" in code
    assert "document.querySelector" not in code


def test_next_control_finder_handles_unlabelled_arrow_widgets():
    assert '.dijitButton, [widgetid]' in CLICK_NEXT_CONTROL_CODE
    assert '[class*="arrow" i]' in CLICK_NEXT_CONTROL_CODE
    assert "appgo" in CLICK_NEXT_CONTROL_CODE.lower()
    assert "back|previous|prev" in CLICK_NEXT_CONTROL_CODE
    assert "selected.el.click()" in CLICK_NEXT_CONTROL_CODE


def test_batch_control_discovery_is_visible_editable_and_unambiguous():
    code = build_batch_repair_code('[{"label":"First Name","value":"Ada"}]')
    assert "aria-hidden=\"true\"" in code
    assert "aria-disabled" in code and "readOnly" in code
    assert "data-automation-id" in code
    assert "ambiguous_control" in code
    assert "interaction_timeout" in code


def test_batch_has_hard_action_budget_and_structured_failure():
    code = build_batch_repair_code('[{"label":"Source","value":"LinkedIn Job Board","type":"combobox"}]')
    assert "browserActions>=12" in code
    assert "action_budget_exhausted" in code
    assert all(key in code for key in ("failure_code", "attempts", "retryable"))
