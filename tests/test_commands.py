"""Tests for the slash-command registry, completer, and /index handler."""

import os
import tempfile

from src.cli.commands import (
    AgentCommandCompleter,
    COMMANDS,
    is_command,
    run_index,
)


class FakeDocument:
    text_before_cursor = "/ind"


def test_command_registry():
    for cmd in ("/index", "/help", "/clear", "/plan"):
        assert cmd in COMMANDS
        assert is_command(cmd)
    assert not is_command("/nope")


def test_completer_matches_prefix():
    got = [c.text for c in AgentCommandCompleter().get_completions(FakeDocument(), None)]
    assert got == ["/index"]


def test_completer_ignores_non_slash():
    class Doc:
        text_before_cursor = "index"
    got = [c.text for c in AgentCommandCompleter().get_completions(Doc(), None)]
    assert got == []


def test_index_generates_explore_md(tmp_path, capsys):
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "__pycache__").mkdir()
        (tmp_path / "src" / "main.py").write_text("print(1)\n")
        (tmp_path / "README.md").write_text("hi\n")

        run_index()

        explore = tmp_path / "explore.md"
        assert explore.exists()
        content = explore.read_text()
        assert "main.py" in content
        assert "README.md" in content
        assert "__pycache__" not in content
    finally:
        os.chdir(old)
