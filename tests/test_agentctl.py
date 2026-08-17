"""Tests for the standalone macOS agent supervisor configuration."""

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "agentctl.py"
SPEC = importlib.util.spec_from_file_location("agentctl", SCRIPT)
agentctl = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(agentctl)


def test_launch_agent_definition_runs_the_agent_module(tmp_path):
    root = tmp_path / "project"
    python = root / ".venv" / "bin" / "python"
    logs = root / "logs" / "agent-service"

    definition = agentctl.launch_agent_definition(root, python, logs)

    assert definition["ProgramArguments"] == [str(python), "-m", "src.agent.app"]
    assert definition["WorkingDirectory"] == str(root)
    assert definition["KeepAlive"] == {"SuccessfulExit": False}
    assert definition["RunAtLoad"] is True
    assert "/.local/bin" in definition["EnvironmentVariables"]["PATH"]


def test_slash_aliases_map_to_service_commands():
    assert agentctl.COMMAND_ALIASES["/start"] == "start"
    assert agentctl.COMMAND_ALIASES["/stop"] == "stop"
    assert agentctl.COMMAND_ALIASES["/restart"] == "restart"
    assert agentctl.COMMAND_ALIASES["/status"] == "status"
    assert agentctl.COMMAND_ALIASES["/send"] == "send"


def test_control_socket_is_under_the_project_log_directory(tmp_path):
    assert agentctl.control_socket_path(tmp_path) == tmp_path / "logs" / "agent-service" / "agent.sock"


def test_launchd_path_includes_the_user_node_bin_before_system_paths(tmp_path):
    path = agentctl.launchd_path(tmp_path)
    assert path.split(":")[:2] == [str(tmp_path / ".local" / "bin"), "/opt/homebrew/bin"]
