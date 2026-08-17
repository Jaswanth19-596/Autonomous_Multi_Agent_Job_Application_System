"""Tests for local control messages sent to a detached agent."""

import asyncio
import tempfile
import uuid
from pathlib import Path

from src.runtime.control_socket import LocalControlSocket
from src.runtime.services import AgentRuntime


def test_local_control_socket_queues_a_message():
    async def exercise_socket():
        runtime = AgentRuntime()
        # macOS limits Unix-domain socket paths to roughly 104 bytes. pytest's
        # per-test directories are deeper than that, so use the short system
        # temp directory while keeping the name unique.
        socket_path = Path(tempfile.gettempdir()) / f"agent-{uuid.uuid4().hex}.sock"
        server = LocalControlSocket(runtime, socket_path)
        await server.start()
        try:
            reader, writer = await asyncio.open_unix_connection(str(socket_path))
            writer.write(b"show pending jobs\n")
            await writer.drain()
            assert await reader.readline() == b"QUEUED\n"
            writer.close()
            await writer.wait_closed()
            assert await runtime.inputs.messages.get() == "show pending jobs"
        finally:
            await server.stop()
        assert not socket_path.exists()

    asyncio.run(exercise_socket())
