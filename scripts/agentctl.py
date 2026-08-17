#!/usr/bin/env python3
"""Install and control the FilePilot macOS launchd service.

The service runs the project's virtual-environment Python as
``python -m src.agent.app`` and relaunches it after an unexpected exit.
Run this script with ``uv run python scripts/agentctl.py <command>``.
"""
from __future__ import annotations

import argparse
import os
import plistlib
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence


LABEL = "com.filepilot.agent"
COMMAND_ALIASES = {
    "/start": "start",
    "/stop": "stop",
    "/restart": "restart",
    "/status": "status",
    "/send": "send",
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def launch_agent_paths(root: Path, home: Path | None = None) -> tuple[Path, Path, Path]:
    """Return the virtualenv Python, launchd plist, and log directory."""
    home = home or Path.home()
    return (
        root / ".venv" / "bin" / "python",
        home / "Library" / "LaunchAgents" / f"{LABEL}.plist",
        root / "logs" / "agent-service",
    )


def control_socket_path(root: Path) -> Path:
    return root / "logs" / "agent-service" / "agent.sock"


def launchd_path(home: Path | None = None) -> str:
    """Return the deterministic PATH required by the managed agent.

    launchd does not inherit an interactive shell PATH. Node is installed in
    ~/.local/bin on this workstation, and Playwright MCP is launched through
    npx, so that directory must be present before the system defaults.
    """
    home = home or Path.home()
    paths = [
        home / ".local" / "bin",
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
        Path("/usr/bin"),
        Path("/bin"),
        Path("/usr/sbin"),
        Path("/sbin"),
    ]
    return ":".join(str(path) for path in paths)


def launch_agent_definition(root: Path, python: Path, logs: Path) -> dict:
    """Build the portable plist payload used by launchd."""
    return {
        "Label": LABEL,
        "ProgramArguments": [str(python), "-m", "src.agent.app"],
        "WorkingDirectory": str(root),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 5,
        "EnvironmentVariables": {"PATH": launchd_path()},
        "StandardOutPath": str(logs / "agent.out.log"),
        "StandardErrorPath": str(logs / "agent.err.log"),
    }


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _target() -> str:
    return f"{_domain()}/{LABEL}"


def _require_macos() -> None:
    if sys.platform != "darwin":
        raise SystemExit("agentctl uses macOS launchd and can only run on macOS.")


def _run_launchctl(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *args],
        text=True,
        check=check,
        capture_output=True,
    )


def _is_loaded() -> bool:
    return _run_launchctl("print", _target(), check=False).returncode == 0


def _unload_if_loaded() -> bool:
    """Unload the service and wait until launchd has fully released it."""
    if not _is_loaded():
        return False
    _run_launchctl("bootout", _target())
    deadline = time.monotonic() + 5
    while _is_loaded() and time.monotonic() < deadline:
        time.sleep(0.1)
    if _is_loaded():
        raise SystemExit("Agent is still unloading. Retry the command in a few seconds.")
    return True


def install(root: Path) -> None:
    """Write the user LaunchAgent plist and start the managed agent."""
    _require_macos()
    python, plist_path, logs = launch_agent_paths(root)
    if not python.is_file():
        raise SystemExit(f"Virtual environment not found at {python}. Run `uv sync` first.")

    logs.mkdir(parents=True, exist_ok=True)
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    _unload_if_loaded()
    with plist_path.open("wb") as handle:
        plistlib.dump(launch_agent_definition(root, python, logs), handle)
    _run_launchctl("bootstrap", _domain(), str(plist_path))
    print(f"Installed and started {LABEL}. Unexpected crashes will restart automatically.")


def start(root: Path) -> None:
    """Start a previously installed LaunchAgent, loading it when necessary."""
    _require_macos()
    _, plist_path, _ = launch_agent_paths(root)
    if not plist_path.is_file():
        raise SystemExit("Agent service is not installed. Run `agentctl.py install` first.")
    if not _is_loaded():
        _run_launchctl("bootstrap", _domain(), str(plist_path))
    else:
        print("Agent is already running.")
        return
    # RunAtLoad starts the process as part of bootstrap. Calling kickstart
    # immediately afterward races that startup and can fail with launchctl
    # exit code 37 even though the plist is valid.
    print("Agent started.")


def stop(root: Path) -> None:
    """Stop and unload the service so launchd will not restart it."""
    _require_macos()
    if _unload_if_loaded():
        print("Agent stopped.")
    else:
        print("Agent is already stopped.")


def status(root: Path) -> None:
    """Show whether launchd currently has the agent loaded."""
    _require_macos()
    result = _run_launchctl("print", _target(), check=False)
    if result.returncode:
        print("Agent is stopped.")
        return
    print("Agent is running under launchd.")
    print(result.stdout.strip())


def restart(root: Path) -> None:
    stop(root)
    start(root)


def logs(root: Path, follow: bool = False) -> None:
    """Print service logs; pass --follow to keep streaming them."""
    _, _, log_dir = launch_agent_paths(root)
    output = log_dir / "agent.out.log"
    errors = log_dir / "agent.err.log"
    log_dir.mkdir(parents=True, exist_ok=True)
    for path in (output, errors):
        path.touch(exist_ok=True)
    command = ["tail", "-n", "100"]
    if follow:
        command.append("-f")
    command.extend([str(output), str(errors)])
    subprocess.run(command, check=True)


def send(root: Path, message: str) -> None:
    """Send one local message to the detached agent's control socket."""
    if not message.strip():
        raise SystemExit("Provide a message, for example: agentctl.py send 'show pending jobs'.")
    path = control_socket_path(root)
    deadline = time.monotonic() + 10
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(2)
                client.connect(str(path))
                client.sendall((message.strip() + "\n").encode("utf-8"))
                response = client.recv(128).decode("utf-8", errors="replace").strip()
            if response == "QUEUED":
                print("Message queued for the agent.")
                return
            raise SystemExit(response or "Agent did not acknowledge the message.")
        except OSError as exc:
            last_error = exc
            time.sleep(0.5)
    raise SystemExit(
        f"Agent control socket is unavailable at {path}. "
        f"Check `agentctl.py status` and logs. Last error: {last_error}"
    )


def uninstall(root: Path) -> None:
    """Unload and remove the launchd plist. Log files are kept."""
    _require_macos()
    _, plist_path, _ = launch_agent_paths(root)
    _unload_if_loaded()
    if plist_path.exists():
        plist_path.unlink()
        print("Agent service removed. Logs were retained.")
    else:
        print("Agent service is not installed.")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Control the FilePilot launchd service.")
    parser.add_argument(
        "command",
        choices=("install", "start", "stop", "restart", "status", "logs", "send", "uninstall", *COMMAND_ALIASES),
        help="Use install once, then start/stop/restart/status/logs/send as needed.",
    )
    parser.add_argument("--follow", action="store_true", help="Keep streaming output for the logs command.")
    parser.add_argument("message", nargs="*", help="Message for the send command.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    command = COMMAND_ALIASES.get(args.command, args.command)
    root = project_root()
    actions = {
        "install": install,
        "start": start,
        "stop": stop,
        "status": status,
        "restart": restart,
        "uninstall": uninstall,
    }
    if command == "logs":
        logs(root, follow=args.follow)
    elif command == "send":
        send(root, " ".join(args.message))
    else:
        actions[command](root)


if __name__ == "__main__":
    main()
