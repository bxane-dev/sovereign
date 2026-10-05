import json
import threading
import urllib.request

from sovereign.agent import SovereignAgent
from sovereign.api import SovereignHTTPServer
from sovereign.config import SovereignConfig
from sovereign.models import BackendReply, BackendSpec, Capability


class FakeExecutor:
    async def complete(self, spec, messages, tools, capability):
        return BackendReply(text="api answer")


def test_api_health_status_route_and_run():
    cfg = SovereignConfig(
        backends=[BackendSpec("local", "http://local", frozenset({Capability.REASONING}), priority=1)]
    )
    server = SovereignHTTPServer(("127.0.0.1", 0), SovereignAgent(cfg, executor=FakeExecutor()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/health") as response:
            assert json.load(response)["ok"] is True
        request = urllib.request.Request(
            f"http://{host}:{port}/v1/route",
            data=json.dumps({"capability": "reasoning"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            body = json.load(response)
        assert body == {"capability": "reasoning", "backend": "local", "attachments": []}

        request = urllib.request.Request(
            f"http://{host}:{port}/v1/run",
            data=json.dumps({"prompt": "hello"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            body = json.load(response)
        assert body["text"] == "api answer"
        assert body["backend"] == "local"
        assert body["steps"] == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
