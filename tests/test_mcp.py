import asyncio
import json
import sys
from pathlib import Path

from sovereign.mcp import MCPClient
from sovereign.models import MCPServerSpec


def test_mcp_stdio_round_trip(tmp_path: Path):
    server = tmp_path / "server.py"
    server.write_text(
        """
import json, sys
for line in sys.stdin:
    req = json.loads(line)
    method = req.get('method')
    if method == 'initialize':
        result = {'protocolVersion': '2025-06-18'}
    elif method == 'tools/list':
        result = {'tools': [{'name': 'echo'}]}
    elif method == 'tools/call':
        result = {'content': [{'type': 'text', 'text': req['params']['arguments'].get('text', '')}]}
    else:
        result = {}
    sys.stdout.write(json.dumps({'jsonrpc':'2.0','id':req['id'],'result':result}) + '\n')
    sys.stdout.flush()
""".strip(),
        encoding="utf-8",
    )

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
