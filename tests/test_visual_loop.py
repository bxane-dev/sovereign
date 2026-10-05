import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sovereign.agent import SovereignAgent
from sovereign.api import create_app
from sovereign.config import SovereignConfig
from sovereign.models import BackendReply, BackendSpec, Capability, ToolCall
from sovereign.native_tools import ApprovalRequired, NativeToolRuntime
from sovereign.permissions import PermissionPolicy


class FakeDesktop:
    def __init__(self):
        self.actions = []
        self.frames = 0

    def screen_size(self):
        return (1280, 720)

    def screenshot(self, path: Path):
        self.frames += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"fake-frame-{self.frames}".encode())
        self.actions.append(("screenshot", self.frames, str(path)))
        return (1280, 720)

    def move_to(self, x, y, duration):
        self.actions.append(("move", x, y, duration))

    def click(self, x, y, button, clicks):
        self.actions.append(("click", x, y, button, clicks))

    def type_text(self, text, interval):
        self.actions.append(("type", text, interval))

    def press_key(self, key):
        self.actions.append(("key", key))

    def hotkey(self, keys):
        self.actions.append(("hotkey", list(keys)))


class VisualExecutor:
    def __init__(self):
        self.calls = 0
        self.messages = []

    async def complete(self, spec, messages, tools, capability):
        self.calls += 1
        self.messages.append((list(messages), list(tools), capability))
        if self.calls == 1:
            return BackendReply(
                text="clicking",
                tool_calls=(
                    ToolCall(
                        "call_1",
                        "sovereign__mouse_click",
                        {"x": 100, "y": 120, "button": "left", "clicks": 1},
                    ),
                ),
            )
        return BackendReply(text="task complete")


def make_agent(tmp_path: Path):
    cfg = SovereignConfig(
        workspace=tmp_path,
        computer_control_enabled=True,
        visual_autonomy_enabled=True,
        visual_action_delay_seconds=0,
        backends=[
            BackendSpec(
                "vision",
                "http://unused",
                frozenset({Capability.VISION}),
                priority=10,
            )
        ],
    )
    desktop = FakeDesktop()
    native = NativeToolRuntime(cfg, PermissionPolicy(cfg), desktop)
    executor = VisualExecutor()
    return SovereignAgent(cfg, executor=executor, native_tools=native), desktop, executor


def test_visual_loop_refreshes_screen_after_each_action(tmp_path: Path):
    agent, desktop, executor = make_agent(tmp_path)

    result = asyncio.run(
        agent.run_visual(
            "click the target",
            approved_tools=["sovereign__mouse_click"],
        )
    )

    assert result.text == "task complete"
    assert result.frames == 2
    assert result.tool_calls == 1
    assert desktop.frames == 2
    assert ("click", 100, 120, "left", 1) in desktop.actions
    assert executor.messages[0][2] is Capability.VISION
    assert executor.messages[0][1][0]["function"]["name"] == "sovereign__mouse_click"


def test_visual_loop_requires_per_run_action_approval(tmp_path: Path):
    agent, _, _ = make_agent(tmp_path)

    with pytest.raises(ApprovalRequired):
        asyncio.run(agent.run_visual("click the target"))


def test_visual_api_endpoint(tmp_path: Path):
    agent, _, _ = make_agent(tmp_path)
    client = TestClient(create_app(agent))

    response = client.post(
        "/v1/computer/run",
        json={
            "prompt": "click the target",
            "approved_tools": ["sovereign__mouse_click"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "task complete"
    assert body["frames"] == 2
    assert body["tool_calls"] == 1
