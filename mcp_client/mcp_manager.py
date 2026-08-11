from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from langchain_core.tools import StructuredTool
import asyncio
import json
import httpx2
from .google_auth import get_gmail_credentials
from .gmail_service import execute_gmail_fallback


class MCPManager:
    """Owns the stdio MCP server connections and exposes their tools to LangChain.

    Each server runs in its own task (see `_serve`). That is deliberate:
    `stdio_client` and `ClientSession` are anyio task groups, so their cancel
    scopes must be entered and exited by the same task in the same order. An
    earlier version entered them through a shared `AsyncExitStack` inside an
    `anyio.fail_after` scope and closed them later, which corrupted the cancel
    scope stack — the timeout surfaced as `RuntimeError: Attempted to exit a
    cancel scope that isn't the current task's current cancel scope` and the app
    hung instead of reporting the slow server.
    """

    def __init__(self, config_path = "servers.json"):
        self.config_path = config_path
        self.sessions = {}
        self.mcp_tools = {}
        self._workers = []
        self._shutdown = asyncio.Event()

    async def connect(self, timeout = 30):
        """Starts every configured server, returning {server_name: error} for any that failed.

        A server that times out or crashes is skipped rather than fatal, so the
        agent still starts with its native tools.
        """
        with open(self.config_path) as f:
            servers = json.load(f).get("mcpServers", {})

        errors = {}

        for name, cfg in servers.items():
            try:
                await self._start_server(name, cfg, timeout)
            except Exception as e:
                errors[name] = e

        return errors

    async def _start_server(self, name, cfg, timeout):

        transport = cfg.get("transport", "stdio")

        if transport == "stdio":

            await self._start_stdio_server(
                name,
                cfg,
                timeout
            )

        elif transport == "streamable_http":

            await self._start_http_server(
                name,
                cfg,
                timeout
            )

        else:

            raise ValueError(
                f"Unsupported MCP transport "
                f"'{transport}' for '{name}'"
            )

    async def _start_stdio_server(
        self,
        name,
        cfg,
        timeout,
    ):

        ready = asyncio.Event()
        box = {}

        worker = asyncio.create_task(
            self._serve_stdio(
                name,
                cfg,
                ready,
                box,
            ),
            name=f"mcp:stdio:{name}",
        )

        self._workers.append(worker)

        try:

            await asyncio.wait_for(
                ready.wait(),
                timeout,
            )

        except asyncio.TimeoutError:

            await self._stop(worker)

            command = " ".join(
                [
                    cfg["command"],
                    *cfg.get("args", []),
                ]
            )

            raise TimeoutError(
                f"MCP server '{name}' did not "
                f"respond within {timeout}s "
                f"(command: {command})"
            ) from None

        if "error" in box:

            await self._stop(worker)

            raise RuntimeError(
                f"MCP server '{name}' failed "
                f"to start: {box['error']}"
            ) from box["error"]



    async def _serve_stdio(
        self,
        server_name,
        cfg,
        ready,
        box,
    ):

        params = StdioServerParameters(
            command=cfg["command"],
            args=cfg.get("args", []),
        )

        try:

            async with stdio_client(params) as (
                read,
                write,
            ):

                async with ClientSession(
                    read,
                    write,
                ) as session:

                    await session.initialize()

                    result = await session.list_tools()

                    for tool in result.tools:

                        key = (
                            server_name,
                            tool.name,
                        )

                        self.sessions[key] = session
                        self.mcp_tools[key] = tool

                    print(
                        f"Connected to MCP server: "
                        f"{server_name}"
                    )

                    ready.set()

                    await self._shutdown.wait()

        except asyncio.CancelledError:
            raise

        except Exception as e:

            box["error"] = e

        finally:

            ready.set()

    async def _start_http_server(
        self,
        name,
        cfg,
        timeout,
    ):

        ready = asyncio.Event()
        box = {}

        worker = asyncio.create_task(
            self._serve_http(
                name,
                cfg,
                ready,
                box,
            ),
            name=f"mcp:http:{name}",
        )

        self._workers.append(worker)

        try:

            await asyncio.wait_for(
                ready.wait(),
                timeout,
            )

        except asyncio.TimeoutError:

            await self._stop(worker)

            raise TimeoutError(
                f"Remote MCP server '{name}' "
                f"did not respond within "
                f"{timeout}s"
            ) from None

        if "error" in box:

            await self._stop(worker)

            raise RuntimeError(
                f"Remote MCP server '{name}' "
                f"failed to start: {box['error']}"
            ) from box["error"]

    async def _serve_http(
        self,
        server_name,
        cfg,
        ready,
        box,
    ):

        try:

            credentials = get_gmail_credentials()

            headers = {
                "Authorization": (
                    f"Bearer {credentials.token}"
                )
            }

            http_client = httpx2.AsyncClient(
                headers=headers,
            )

            async with streamable_http_client(
                cfg["serverUrl"],
                http_client=http_client,
            ) as (
                read,
                write,
            ):

                async with ClientSession(
                    read,
                    write,
                ) as session:

                    await session.initialize()

                    result = await session.list_tools()

                    for tool in result.tools:

                        key = (
                            server_name,
                            tool.name,
                        )

                        self.sessions[key] = session
                        self.mcp_tools[key] = tool

                    print(
                        f"Connected to remote MCP "
                        f"server: {server_name}"
                    )

                    print(
                        f"Gmail MCP tools: "
                        f"{len(result.tools)}"
                    )

                    ready.set()

                    await self._shutdown.wait()

        except asyncio.CancelledError:
            raise

        except Exception as e:

            box["error"] = e

        finally:

            ready.set()

    @staticmethod
    async def _stop(worker):
        worker.cancel()
        # asyncio.wait never re-raises the task's exception, so a failed or
        # cancelled worker cannot mask the error we are about to report.
        await asyncio.wait({worker}, timeout = 10)


    async def call_tool(
        self,
        server_name,
        tool_name,
        args,
    ):

        key = (
            server_name,
            tool_name,
        )

        session = self.sessions[key]

        result = await session.call_tool(
            tool_name,
            arguments=args,
        )

        output = "\n".join(
            block.text
            for block in result.content
            if block.type == "text"
        )

        if server_name == "gmail" and ("The caller does not have permission" in output or "Permission denied" in output):
            return await execute_gmail_fallback(tool_name, args)

        return output
    async def get_langchain_tools(self):

        tools = []

        for (
            server_name,
            tool_name,
        ), tool in self.mcp_tools.items():

            async def run(
                _server=server_name,
                _tool=tool_name,
                **kwargs,
            ):

                return await self.call_tool(
                    _server,
                    _tool,
                    kwargs,
                )

            tools.append(
                StructuredTool.from_function(
                    coroutine=run,
                    name=f"{server_name}_{tool_name}",
                    description=tool.description or "",
                    args_schema=tool.input_schema,
                )
            )

        return tools

    async def close(self):
        if not self._workers:
            return

        self._shutdown.set()

        _, pending = await asyncio.wait(self._workers, timeout = 10)

        for worker in pending:
            worker.cancel()

        if pending:
            await asyncio.wait(pending, timeout = 10)

        self._workers.clear()
        self.sessions.clear()
        self.mcp_tools.clear()
