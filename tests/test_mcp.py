import asyncio
import sys
from pathlib import Path

from sovereign.mcp import MCPClient, MCPHub
from sovereign.models import MCPServerSpec


def make_server(tmp_path: Path) -> Path:
    server = tmp_path / "server.py"
    server.write_text(
        r'''
import json, sys
for line in sys.stdin:
    req = json.loads(line)
    if "id" not in req:
        continue
    method = req.get("method")
    if method == "initialize":
        result = {"protocolVersion": "2025-06-18"}
    elif method == "tools/list":
        result = {"tools": [{"name": "echo", "description": "Echo text", "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}}}]}
    elif method == "tools/call":
        result = {"content": [{"type": "text", "text": req["params"]["arguments"].get("text", "")}]}
    else:
        result = {}
    sys.stdout.write(json.dumps({"jsonrpc":"2.0","id":req["id"],"result":result}) + "\n")
    sys.stdout.flush()
'''.strip(),
        encoding="utf-8",
    )
    return server


def test_mcp_stdio_round_trip(tmp_path: Path):
    server = make_server(tmp_path)

    async def scenario():
        client = MCPClient(MCPServerSpec("test", (sys.executable, str(server))))
        try:
            init = await client.initialize()
            tools = await client.list_tools()
            called = await client.call_tool("echo", {"text": "hi"})
            assert init["protocolVersion"] == "2025-06-18"
            assert tools["tools"][0]["name"] == "echo"
            assert called["content"][0]["text"] == "hi"
        finally:
            await client.close()

    asyncio.run(scenario())


def test_hub_namespaces_discovered_tools(tmp_path: Path):
    server = make_server(tmp_path)

    async def scenario():
        hub = MCPHub([MCPServerSpec("local tools", (sys.executable, str(server)))])
        clients, definitions, registry = await hub.connect_tools()
        try:
            assert definitions[0]["function"]["name"] == "local_tools__echo"
            assert registry["local_tools__echo"] == ("local tools", "echo")
        finally:
            await asyncio.gather(*(client.close() for client in clients.values()))

    asyncio.run(scenario())
