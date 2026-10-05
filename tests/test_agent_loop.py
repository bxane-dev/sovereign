import asyncio

from sovereign.agent import SovereignAgent
from sovereign.backend import BackendExecutionError
from sovereign.config import SovereignConfig
from sovereign.models import BackendReply, BackendSpec, Capability, ToolCall


class FakeExecutor:
    def __init__(self):
        self.calls = 0
        self.messages = []

    async def complete(self, spec, messages, tools, capability):
        self.calls += 1
        self.messages.append(list(messages))
        if self.calls == 1:
            return BackendReply(
                text="",
                tool_calls=(ToolCall("call_1", "srv__echo", {"text": "hello"}),),
            )
        return BackendReply(text="tool result received")


class FakeClient:
    def __init__(self):
        self.closed = False
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return {"content": [{"type": "text", "text": arguments["text"]}]}

    async def close(self):
        self.closed = True


class FakeHub:
    def __init__(self, client):
        self._client = client

    def names(self):
        return ["srv"]

    async def connect_tools(self):
        return (
            {"srv": self._client},
            [{"type": "function", "function": {"name": "srv__echo", "parameters": {"type": "object"}}}],
            {"srv__echo": ("srv", "echo")},
        )


def test_agent_executes_tool_and_returns_final_answer():
    executor = FakeExecutor()
    client = FakeClient()
    cfg = SovereignConfig(
        backends=[BackendSpec("model", "http://unused", frozenset({Capability.REASONING}))]
    )
    agent = SovereignAgent(cfg, executor=executor)
    agent.mcp = FakeHub(client)
    result = asyncio.run(agent.run("use the tool"))
    assert result.text == "tool result received"
    assert result.steps == 2
    assert result.tool_calls == 1
    assert client.calls == [("echo", {"text": "hello"})]
    assert client.closed is True
    assert executor.messages[1][-1]["role"] == "tool"


class FailingExecutor:
    async def complete(self, spec, messages, tools, capability):
        if spec.name == "primary":
            raise BackendExecutionError("primary down")
        return BackendReply(text="fallback ok")


def test_agent_fails_over_to_next_backend():
    cfg = SovereignConfig(
        backends=[
            BackendSpec("primary", "http://a", frozenset({Capability.REASONING}), priority=10),
            BackendSpec("backup", "http://b", frozenset({Capability.REASONING}), priority=1),
        ]
    )
    result = asyncio.run(SovereignAgent(cfg, executor=FailingExecutor()).run("hello"))
    assert result.backend == "backup"
    assert result.text == "fallback ok"
