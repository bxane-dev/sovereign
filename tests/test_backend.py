import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from sovereign.backend import BackendExecutor
from sovereign.models import BackendSpec, Capability


class Handler(BaseHTTPRequestHandler):
    payload = None
    authorization = None
    path_seen = None

    def log_message(self, format, *args):
        return

    def do_POST(self):
        Handler.path_seen = self.path
        length = int(self.headers["Content-Length"])
        Handler.payload = json.loads(self.rfile.read(length))
        Handler.authorization = self.headers.get("Authorization")
        body = json.dumps(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": "demo",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "checking",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "tools__echo", "arguments": '{"text":"hi"}'},
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_openai_backend_uses_official_async_sdk(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    monkeypatch.setenv("TOKEN", "Bearer secret")
    spec = BackendSpec(
        name="local",
        endpoint=f"http://{host}:{port}/v1/chat/completions",
        capabilities=frozenset({Capability.REASONING}),
        headers={"Authorization": "env:TOKEN"},
        model="demo",
    )
    try:
        reply = asyncio.run(
            BackendExecutor().complete(
                spec,
                [{"role": "user", "content": "hello"}],
                [{"type": "function", "function": {"name": "tools__echo", "parameters": {"type": "object"}}}],
                Capability.REASONING,
            )
        )
        assert Handler.path_seen == "/v1/chat/completions"
        assert Handler.payload["model"] == "demo"
        assert Handler.authorization == "Bearer secret"
        assert reply.text == "checking"
        assert reply.tool_calls[0].name == "tools__echo"
        assert reply.tool_calls[0].arguments == {"text": "hi"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
