import asyncio

from sovereign.agent import SovereignAgent
from sovereign.config import SovereignConfig
from sovereign.models import BackendReply, BackendSpec, Capability, ToolCall


class FakeExecutor:
    def __init__(self):
        self.calls = 0
        self.messages = []

    async def complete(self, spec, messages, tools, capability):
        self.calls += 1
        self.messages.append((list(messages), list(tools)))
        if self.calls == 1:
            return BackendReply(
                text="",
                tool_calls=(ToolCall("call_1", "sovereign__demo", {"value": "x"}),),
            )
        return BackendReply(text="native tool complete")


class FakeNativeTools:
    def __init__(self):
        self.calls = []

    def definitions(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "sovereign__demo",
                    "description": "demo",
                    "parameters": {"type": "object"},
                },
            }
        ]

    def names(self):
        return ["sovereign__demo"]

    async def execute(self, name, arguments, approved_tools=()):
        self.calls.append((name, arguments, list(approved_tools)))
        return {"ok": True}


def test_agent_merges_and_executes_native_tools():
    executor = FakeExecutor()
    native = FakeNativeTools()
    cfg = SovereignConfig(
        backends=[BackendSpec("model", "http://unused", frozenset({Capability.REASONING}))]
    )
    agent = SovereignAgent(cfg, executor=executor, native_tools=native)

    result = asyncio.run(
        agent.run(
            "use the native tool",
            approved_tools=["sovereign__demo"],
        )
    )

    assert result.text == "native tool complete"
    assert result.tool_calls == 1
    assert native.calls == [
        ("sovereign__demo", {"value": "x"}, ["sovereign__demo"])
    ]
    assert executor.messages[0][1][0]["function"]["name"] == "sovereign__demo"
    assert executor.messages[1][0][-1]["role"] == "tool"
