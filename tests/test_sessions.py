import asyncio

import pytest
from fastapi.testclient import TestClient

from sovereign.agent import SovereignAgent
from sovereign.api import create_app
from sovereign.backend import BackendExecutionError
from sovereign.config import SovereignConfig
from sovereign.models import BackendReply, BackendSpec, Capability
from sovereign.sessions import SessionError


class RecordingExecutor:
    def __init__(self):
        self.messages = []
        self.fail = False

    async def complete(self, spec, messages, tools, capability):
        self.messages.append(list(messages))
        if self.fail:
            raise BackendExecutionError("temporary outage")
        return BackendReply(text=f"reply {len(self.messages)}")


def make_agent(tmp_path, executor):
    config = SovereignConfig(
        workspace=tmp_path,
        backends=[BackendSpec("local", "http://unused", frozenset({Capability.REASONING}))],
    )
    return SovereignAgent(config, executor=executor)


def test_session_history_survives_agent_restart(tmp_path):
    executor = RecordingExecutor()
    agent = make_agent(tmp_path, executor)
    session = agent.sessions.create()
    asyncio.run(agent.run("first", session_id=session.id))

    restarted = make_agent(tmp_path, executor)
    result = asyncio.run(restarted.run("second", session_id=session.id))
    assert result.text == "reply 2"
    assert [message["role"] for message in executor.messages[1]] == [
        "user", "assistant", "user"
    ]
    assert restarted.sessions.get(session.id).status == "completed"


def test_interrupted_session_resumes_without_replaying_uncertain_action(tmp_path):
    executor = RecordingExecutor()
    agent = make_agent(tmp_path, executor)
    session = agent.sessions.create()
    messages = [
        {"role": "user", "content": "do it"},
        {
            "role": "assistant", "content": None,
            "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "sovereign__write_text", "arguments": "{}"},
            }],
        },
    ]
    agent.sessions.checkpoint(session.id, messages, "running")

    restarted = make_agent(tmp_path, executor)
    assert restarted.sessions.get(session.id).status == "interrupted"
    result = asyncio.run(restarted.run("", session_id=session.id, resume=True))
    assert result.text == "reply 1"
    assert "outcome is unknown" in executor.messages[0][-1]["content"]
    assert executor.messages[0][-1]["tool_call_id"] == "call_1"
    assert restarted.sessions.get(session.id).status == "completed"


def test_failed_run_is_resumable_and_new_prompt_requires_resume(tmp_path):
    executor = RecordingExecutor()
    executor.fail = True
    agent = make_agent(tmp_path, executor)
    session = agent.sessions.create()
    with pytest.raises(BackendExecutionError):
        asyncio.run(agent.run("first", session_id=session.id))
    assert agent.sessions.get(session.id).status == "interrupted"
    with pytest.raises(SessionError, match="resume the interrupted"):
        asyncio.run(agent.run("second", session_id=session.id))
    executor.fail = False
    assert asyncio.run(agent.run("", session_id=session.id, resume=True)).text == "reply 2"


def test_session_api_create_run_inspect_list_delete(tmp_path):
    agent = make_agent(tmp_path, RecordingExecutor())
    client = TestClient(create_app(agent))
    created = client.post("/v1/sessions", json={}).json()
    session_id = created["id"]
    assert created["status"] == "idle"
    response = client.post("/v1/run", json={"prompt": "hello", "session_id": session_id})
    assert response.status_code == 200
    assert client.get(f"/v1/sessions/{session_id}").json()["message_count"] == 2
    assert len(client.get("/v1/sessions").json()["sessions"]) == 1
    assert client.delete(f"/v1/sessions/{session_id}").status_code == 204
    assert client.get(f"/v1/sessions/{session_id}").status_code == 404
