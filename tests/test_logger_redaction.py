from src.core import logging as logger


def test_nested_sensitive_values_are_redacted_from_log(tmp_path, capsys):
    logger.current_log_file_var.set(tmp_path / "job.log")
    payload = {"outer": {"password": "fake-password", "headers": {"Authorization": "Bearer fake-token"}}, "otp": "123456"}
    logger.log_event("TOOL_CALL", payload)
    output = (tmp_path / "job.log").read_text(encoding="utf-8")
    assert "fake-password" not in output
    assert "fake-token" not in output
    assert "123456" not in output
    assert output.count("[REDACTED]") == 3


def test_inline_secret_assignment_is_redacted():
    safe = logger.redact_sensitive("password=hunter2 Authorization: Bearer abc123")
    assert "hunter2" not in safe and "abc123" not in safe


def test_legacy_stringified_tool_arguments_are_redacted():
    safe = logger.redact_sensitive("Args: {'password': 'hunter2', 'otp': '123456'}")
    assert "hunter2" not in safe and "123456" not in safe


def test_all_credential_key_variants_are_redacted():
    payload = {"password": "a", "token": "b", "cookie": "c", "api_key": "d",
               "otp": "e", "authorization": "Bearer f"}
    safe = logger.redact_sensitive(payload)
    assert set(safe.values()) == {"[REDACTED]"}
