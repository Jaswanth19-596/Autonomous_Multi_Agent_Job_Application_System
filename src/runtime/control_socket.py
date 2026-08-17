"""Local command socket for a launchd-managed agent without a terminal."""
from __future__ import annotations

import asyncio
from pathlib import Path

from src.runtime.services import AgentRuntime


def default_socket_path() -> Path:
    return Path(__file__).resolve().parents[2] / "logs" / "agent-service" / "agent.sock"


class LocalControlSocket:
    """Accept local messages and queue them for the manager agent.

    A Unix socket is only reachable by the local macOS user. It provides an
    input channel when launchd runs the app without a terminal attached.
    """

    def __init__(self, runtime: AgentRuntime, path: Path | None = None) -> None:
        self.runtime = runtime
        self.path = path or default_socket_path()
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() or self.path.is_symlink():
            self.path.unlink()
        self._server = await asyncio.start_unix_server(self._handle_connection, path=str(self.path))
        self.path.chmod(0o600)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if self.path.exists() or self.path.is_symlink():
            self.path.unlink()

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            raw_message = await reader.readline()
            message = raw_message.decode("utf-8", errors="replace").strip()
            if not message:
                writer.write(b"ERROR: message cannot be empty\n")
            else:
                await self.runtime.inputs.submit_message(message)
                writer.write(b"QUEUED\n")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
