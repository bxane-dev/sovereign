from fastapi.testclient import TestClient

from sovereign.agent import SovereignAgent
from sovereign.api import create_app
from sovereign.config import SovereignConfig
from sovereign.models import BackendReply, BackendSpec, Capability


class FakeExecutor:
    async def complete(self, spec, messages, tools, capability):
        return BackendReply(text="api answer")


def test_api_health_status_route_and_run():
    cfg = SovereignConfig(
        backends=[BackendSpec("local", "http://local", frozenset({Capability.REASONING}), priority=1)]
    )
    client = TestClient(create_app(SovereignAgent(cfg, executor=FakeExecutor())))

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True

    route = client.post("/v1/route", json={"capability": "reasoning"})
    assert route.status_code == 200
    assert route.json() == {"capability": "reasoning", "backend": "local", "attachments": []}

    run = client.post("/v1/run", json={"prompt": "hello"})
    assert run.status_code == 200
    assert run.json()["text"] == "api answer"
    assert run.json()["backend"] == "local"
    assert run.json()["steps"] == 1


def test_api_uses_pydantic_validation():
    cfg = SovereignConfig(
        backends=[BackendSpec("local", "http://local", frozenset({Capability.REASONING}))]
    )
    client = TestClient(create_app(SovereignAgent(cfg, executor=FakeExecutor())))
    response = client.post("/v1/run", json={"prompt": "", "max_steps": 0})
    assert response.status_code == 422
