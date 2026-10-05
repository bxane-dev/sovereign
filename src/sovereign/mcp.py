from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any

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

    async def _request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        await self.start()
        assert self.process and self.process.stdin and self.process.stdout
        request_id = self._next_id
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        self.process.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        await self.process.stdin.drain()
        while True:
            line = await self.process.stdout.readline()
            if not line:
                raise MCPError(f"MCP server {self.spec.name!r} closed stdout")
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
        return await self._request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "sovereign", "version": "6.6.0"},
            },
        )

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
