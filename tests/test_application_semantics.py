import json

from src.application.semantics import (
    AUDIT_PAGE_CODE, DROPDOWNS_CODE, PAGE_SCHEMA_CODE, RADIO_GROUPS_CODE, CandidateProfileStore,
    build_advance_code, build_fill_dropdowns_code, build_fill_page_code,
    build_fill_radio_groups_code, build_upload_code, resolve_answers,
)


def test_page_schema_is_compact_and_covers_application_controls():
    assert all(x in PAGE_SCHEMA_CODE for x in ("validation_errors", "upload_fields", "captcha_present", "clearcompany"))
    assert "document.body.outerHTML" not in PAGE_SCHEMA_CODE


def test_fill_program_is_semantic_and_verified():
    code = build_fill_page_code({"Last Name": "Mada", "SMS consent": True})
    assert '"Last Name": "Mada"' in code
    assert all(x in code for x in ("setChecked", "selectOption", "getByRole('option'", "filled_and_verified"))
    assert "ANSWERS" not in code


def test_radio_tools_group_questions_and_verify_selection():
    assert all(x in RADIO_GROUPS_CODE for x in ("radio_groups", "question", "options", "fieldset"))
    code = build_fill_radio_groups_code([{"key": "sponsorship", "option": "No"}])
    assert all(x in code for x in ("sponsorship", "await chosen.check()", "filled_and_verified"))


def test_dropdown_tools_inspect_native_and_custom_options_and_fill():
    assert all(x in DROPDOWNS_CODE for x in ("select, [role=combobox]", "[role=option]", "options"))
    code = build_fill_dropdowns_code([{"key": "country", "option": "United States"}])
    assert all(x in code for x in ("selectOption", "getByRole('option'", "filled_and_verified"))


def test_audit_reports_readiness_and_actionable_failures():
    assert all(x in AUDIT_PAGE_CODE for x in ("ready_to_continue", "missing_required", "validationMessage"))


def test_upload_program_targets_file_input_and_verifies_filename(tmp_path):
    path = tmp_path / "resume.pdf"
    code = build_upload_code(str(path), "resume")
    assert "setInputFiles" in code and "Array.from(el.files" in code and str(path) in code
    assert "already_present:true" in code
    assert "getByText(fileName, {exact: true})" in code
    assert "await radio.check()" in code


def test_advance_program_returns_transition_evidence():
    code = build_advance_code("continue")
    assert "save and continue" in code.lower() and "before_url" in code


def test_resolver_uses_provenance_and_never_guesses():
    result = resolve_answers(
        [{"label": "Email", "required": True},
         {"label": "Professional reference email", "required": True},
         {"label": "Disability", "required": True}],
        {"email": "candidate@example.com"},
    )
    assert result["resolved"]["Email"]["source"] == "candidate_profile.email"
    assert result["needs_user"][0]["field"] == "Professional reference email"
    assert result["policy_blocked"][0]["field"] == "Disability"


def test_candidate_profile_store_tracks_source_and_reuse(tmp_path):
    store = CandidateProfileStore(tmp_path / "candidate_profile.json")
    store.update({"email": "candidate@example.com"}, source="user", reusable=True)
    store.update({"one_time": "secret"}, source="application", reusable=False)
    assert store.plain_values() == {"email": "candidate@example.com"}
    assert json.loads(store.path.read_text())["values"]["email"]["source"] == "user"


def test_workday_engine_filters_hidden_helpers_and_bounds_retries():
    code = build_fill_page_code({"Country Phone Code": "+1"})
    assert "aria-hidden=\"true\"" in code
    assert "wd-browser-id" in code
    assert "ambiguous_control" in code
    assert "timeout:4000" in code
    assert "strategies=['pointer','keyboard']" in code


def test_unnamed_radios_never_build_an_empty_name_selector():
    assert "el.name\n                ?" in PAGE_SCHEMA_CODE
    assert "radioOwner" in AUDIT_PAGE_CODE and "radioMembers" in AUDIT_PAGE_CODE
    assert "CSS.escape(el.name)" in PAGE_SCHEMA_CODE


def test_simplify_overlay_controls_are_excluded_everywhere():
    for code in (PAGE_SCHEMA_CODE, AUDIT_PAGE_CODE, build_fill_page_code({"First Name": "Ada"})):
        assert "data-simplify-overlay" in code


def test_workday_combobox_requires_committed_option():
    code = build_fill_dropdowns_code([{"key": "source--source", "option": "LinkedIn Job Board"}])
    assert "option_not_committed" in code
    assert "aria-invalid" in code
    assert "exact:true" in code


def test_dropdown_verifies_visible_selected_state_not_only_input_value():
    code = build_fill_dropdowns_code([{"key": "source", "option": "LinkedIn"}])
    assert "aria-valuetext" in code
    assert "[class*=\"chip\" i]" in code
    assert "closeStaleListboxes" in code
    assert "selectedText" in code
