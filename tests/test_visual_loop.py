import asyncio
import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sovereign.agent import SovereignAgent
from sovereign.agent import AgentStepLimit, ToolExecutionError
from sovereign.api import create_app
from sovereign.backend import BackendExecutionError
from sovereign.config import SovereignConfig
from sovereign.models import BackendReply, BackendSpec, Capability, ToolCall
from sovereign.native_tools import ApprovalRequired, NativeToolError, NativeToolRuntime
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
    tool_names = {item["function"]["name"] for item in executor.messages[0][1]}
    assert "sovereign__mouse_click" in tool_names
    first_frame = executor.messages[0][0][-1]["content"][1]["image_url"]["url"]
    second_frame = executor.messages[1][0][-1]["content"][1]["image_url"]["url"]
    assert base64.b64decode(first_frame.split(",", 1)[1]) == b"fake-frame-1"
    assert base64.b64decode(second_frame.split(",", 1)[1]) == b"fake-frame-2"
    assert executor.messages[1][0][-2]["role"] == "tool"


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


def test_capture_retries_without_calling_backend_on_failed_frames(tmp_path: Path):
    agent, desktop, executor = make_agent(tmp_path)
    agent.config.visual_capture_retries = 2
    agent.config.visual_retry_delay_seconds = 0
    original = desktop.screenshot
    attempts = 0

    def flaky_capture(path):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise NativeToolError("capture temporarily unavailable")
        return original(path)

    desktop.screenshot = flaky_capture
    result = asyncio.run(agent.run_visual("click", approved_tools=["sovereign__mouse_click"]))
    assert result.frames == 2
    assert attempts == 4
    assert executor.calls == 2


def test_capture_exhaustion_stops_before_model_or_action(tmp_path: Path):
    agent, desktop, executor = make_agent(tmp_path)
    agent.config.visual_capture_retries = 1
    agent.config.visual_retry_delay_seconds = 0
    desktop.screenshot = lambda path: (_ for _ in ()).throw(NativeToolError("no display"))

    with pytest.raises(ToolExecutionError, match="screen capture failed after 2 attempts"):
        asyncio.run(agent.run_visual("click", approved_tools=["sovereign__mouse_click"]))
    assert executor.calls == 0
    assert desktop.actions == []


def test_backend_retries_then_fails_over_without_poisoning_next_run(tmp_path: Path):
    agent, desktop, _ = make_agent(tmp_path)
    agent.config.visual_backend_retries = 1
    agent.config.visual_retry_delay_seconds = 0
    agent.mesh.register(BackendSpec("backup", "http://unused", frozenset({Capability.VISION}), priority=1))

    class FlakyExecutor:
        def __init__(self):
            self.calls = []
            self.primary_works = False

        async def complete(self, spec, messages, tools, capability):
            self.calls.append(spec.name)
            if spec.name == "vision" and not self.primary_works:
                raise BackendExecutionError("offline")
            return BackendReply(text="done")

    executor = FlakyExecutor()
    agent.executor = executor
    first = asyncio.run(agent.run_visual("inspect"))
    assert first.backend == "backup"
    assert executor.calls == ["vision", "vision", "backup"]
    executor.primary_works = True
    second = asyncio.run(agent.run_visual("inspect"))
    assert second.backend == "vision"
    assert agent.mesh.route(Capability.VISION).name == "vision"
    assert desktop.frames == 2


def test_action_failure_is_reported_and_rechecked_on_fresh_frame(tmp_path: Path):
    agent, desktop, _ = make_agent(tmp_path)
    original = desktop.click
    attempts = 0

    def flaky_click(x, y, button, clicks):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise NativeToolError("target moved")
        original(x, y, button, clicks)

    desktop.click = flaky_click

    class RecoveryExecutor(VisualExecutor):
        async def complete(self, spec, messages, tools, capability):
            self.calls += 1
            self.messages.append((list(messages), list(tools), capability))
            if self.calls < 3:
                return BackendReply(text="", tool_calls=(ToolCall(f"call_{self.calls}", "sovereign__mouse_click", {"x": 100, "y": 120}),))
            return BackendReply(text="verified")

    recovery = RecoveryExecutor()
    agent.executor = recovery
    result = asyncio.run(agent.run_visual("click", approved_tools=["sovereign__mouse_click"]))
    assert result.text == "verified"
    assert result.frames == 3
    assert result.tool_calls == 2
    assert attempts == 2
    assert desktop.frames == 3
    assert '"ok":false' in recovery.messages[1][0][-2]["content"]
    assert "target moved" in recovery.messages[1][0][-2]["content"]


def test_action_recovery_has_bounded_failure_budget(tmp_path: Path):
    agent, desktop, _ = make_agent(tmp_path)
    agent.config.max_visual_recoveries = 1
    desktop.click = lambda *args: (_ for _ in ()).throw(NativeToolError("stuck"))

    class RepeatingExecutor:
        def __init__(self):
            self.calls = 0

        async def complete(self, spec, messages, tools, capability):
            self.calls += 1
            return BackendReply(text="", tool_calls=(ToolCall(f"call_{self.calls}", "sovereign__mouse_click", {"x": 1, "y": 1}),))

    agent.executor = RepeatingExecutor()
    with pytest.raises(ToolExecutionError, match="visual action failed 2 times"):
        asyncio.run(agent.run_visual("click", approved_tools=["sovereign__mouse_click"]))
    assert desktop.frames == 2


def test_last_frame_never_executes_unverifiable_action(tmp_path: Path):
    agent, desktop, _ = make_agent(tmp_path)
    with pytest.raises(AgentStepLimit, match="before an action could be verified"):
        asyncio.run(agent.run_visual("click", approved_tools=["sovereign__mouse_click"], max_steps=1))
    assert desktop.frames == 1
    assert not any(action[0] == "click" for action in desktop.actions)
