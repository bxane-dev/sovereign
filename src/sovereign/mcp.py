from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from typing import Any

from . import __version__
from .models import MCPServerSpec


class MCPError(RuntimeError):
    pass


@dataclass(slots=True)
class MCPClient:
    spec: MCPServerSpec
    process: asyncio.subprocess.Process | None = None
    _next_id: int = 1

    async def start(self) -> None:
        if self.process is not None:
            return
        env = os.environ.copy()
        env.update(self.spec.env)
        self.process = await asyncio.create_subprocess_exec(
            *self.spec.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

    async def close(self) -> None:
        if self.process is None:
            return
        self.process.terminate()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=2)
        except asyncio.TimeoutError:
            self.process.kill()
            await self.process.wait()
        self.process = None

    async def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        await self.start()
        assert self.process and self.process.stdin
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self.process.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        await self.process.stdin.drain()

    async def _request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        await self.start()
        assert self.process and self.process.stdin and self.process.stdout
        request_id = self._next_id
        self._next_id += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        self.process.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        await self.process.stdin.drain()
        while True:
            line = await self.process.stdout.readline()
            if not line:
                stderr = b""
                if self.process.stderr:
                    try:
                        stderr = await asyncio.wait_for(self.process.stderr.read(), timeout=0.1)
                    except asyncio.TimeoutError:
                        pass
                suffix = f": {stderr.decode('utf-8', 'replace')[:500]}" if stderr else ""
                raise MCPError(f"MCP server {self.spec.name!r} closed stdout{suffix}")
            try:
                response = json.loads(line)
            except json.JSONDecodeError:
                continue
            if response.get("id") != request_id:
                continue
            if "error" in response:
                raise MCPError(str(response["error"]))
            return response.get("result")

    async def initialize(self) -> Any:
        result = await self._request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "sovereign", "version": __version__},
            },
        )
        await self._notify("notifications/initialized")
        return result

    async def list_tools(self) -> Any:
        return await self._request("tools/list", {})

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        return await self._request("tools/call", {"name": name, "arguments": arguments or {}})


class MCPHub:
    def __init__(self, specs: list[MCPServerSpec]):
        self.specs = {spec.name: spec for spec in specs if spec.enabled}

    def names(self) -> list[str]:
        return sorted(self.specs)

    def client(self, name: str) -> MCPClient:
        return MCPClient(self.specs[name])

    @staticmethod
    def _alias(server: str, tool: str) -> str:
        alias = re.sub(r"[^A-Za-z0-9_-]", "_", f"{server}__{tool}")
        return alias[:64]

    async def connect_tools(
        self,
    ) -> tuple[dict[str, MCPClient], list[dict[str, Any]], dict[str, tuple[str, str]]]:
        clients: dict[str, MCPClient] = {}
        definitions: list[dict[str, Any]] = []
        registry: dict[str, tuple[str, str]] = {}
        try:
            for server_name in self.names():
                client = self.client(server_name)
                clients[server_name] = client
                await client.initialize()
                listing = await client.list_tools()
                tools = listing.get("tools", []) if isinstance(listing, dict) else []
                for tool in tools:
                    if not isinstance(tool, dict) or not tool.get("name"):
                        continue
                    real_name = str(tool["name"])
                    alias = self._alias(server_name, real_name)
                    if alias in registry:
                        raise MCPError(f"MCP tool alias collision: {alias}")
                    schema = tool.get("inputSchema") or {"type": "object", "properties": {}}
                    if not isinstance(schema, dict):
                        schema = {"type": "object", "properties": {}}
                    registry[alias] = (server_name, real_name)
                    definitions.append(
                        {
                            "type": "function",
                            "function": {
                                "name": alias,
                                "description": str(tool.get("description", "")),
                                "parameters": schema,
                            },
                        }
                    )
            return clients, definitions, registry
        except Exception:
            await asyncio.gather(*(client.close() for client in clients.values()), return_exceptions=True)
            raise
