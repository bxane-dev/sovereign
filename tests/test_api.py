import json

from fastapi.testclient import TestClient

from sovereign.agent import SovereignAgent
from sovereign.api import create_app, serve
from sovereign.config import SovereignConfig
from sovereign.models import BackendReply, BackendSpec, Capability


class FakeExecutor:
    async def complete(self, spec, messages, tools, capability):
        return BackendReply(text="api answer")


def test_api_health_status_route_run_and_tools():
    cfg = SovereignConfig(
        backends=[BackendSpec("local", "http://local", frozenset({Capability.REASONING}), priority=1)]
    )
    client = TestClient(create_app(SovereignAgent(cfg, executor=FakeExecutor())))

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True

    tools = client.get("/v1/tools")
    assert tools.status_code == 200
    assert "sovereign__read_text" in tools.json()["native_tools"]

    route = client.post("/v1/route", json={"capability": "reasoning"})
    assert route.status_code == 200
    assert route.json() == {"capability": "reasoning", "backend": "local", "attachments": []}

    run = client.post(
        "/v1/run",
        json={"prompt": "hello", "approved_tools": ["sovereign__write_text"]},
    )
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


def test_computer_control_setting_requires_explicit_request_and_preserves_config(monkeypatch, tmp_path):
    from sovereign import api

    config_path = tmp_path / "config.json"
    config_path.write_text('{"workspace":"kept","backends":[]}', encoding="utf-8")
    monkeypatch.setattr(api, "DEFAULT_CONFIG", config_path)
    agent = SovereignAgent(SovereignConfig(workspace=tmp_path))
    client = TestClient(create_app(agent))

    response = client.post("/v1/settings/computer-control", json={"enabled": True})

    assert response.status_code == 200
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["workspace"] == "kept"
    assert saved["computer_control_enabled"] is True
    assert saved["visual_autonomy_enabled"] is True
    assert agent.config.computer_control_enabled is True
    assert agent.config.visual_autonomy_enabled is True
    assert "sovereign__mouse_click" in response.json()["native_tools"]


def test_api_token_rejects_untrusted_local_requests(monkeypatch, tmp_path):
    monkeypatch.setenv("SOVEREIGN_API_TOKEN", "private-test-token")
    cfg = SovereignConfig(
        workspace=tmp_path,
        backends=[BackendSpec("local", "http://local", frozenset({Capability.REASONING}))],
    )
    client = TestClient(create_app(SovereignAgent(cfg, executor=FakeExecutor())))
    assert client.get("/health").status_code == 401
    assert client.get("/health", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/health", headers={"Authorization": "Bearer private-test-token"}).status_code == 200


def test_non_loopback_server_requires_token(monkeypatch, tmp_path):
    monkeypatch.delenv("SOVEREIGN_API_TOKEN", raising=False)
    agent = SovereignAgent(SovereignConfig(workspace=tmp_path))
    import pytest
    with pytest.raises(ValueError, match="requires SOVEREIGN_API_TOKEN"):
        serve(agent, "0.0.0.0")
