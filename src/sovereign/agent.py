from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from . import __version__
from .attachments import AttachmentError, AttachmentInspector
from .backend import BackendExecutionError, BackendExecutor
from .config import SovereignConfig
from .mcp import MCPHub
from .mesh import ComputeMesh, NoBackendAvailable
from .models import (
    Attachment,
    BackendReply,
    BackendSpec,
    Capability,
    RunResult,
    VisualRunResult,
)
from .native_tools import NativeToolError, NativeToolRuntime
from .permissions import PermissionPolicy


@dataclass(frozen=True, slots=True)
class RouteDecision:
    capability: Capability
    backend: BackendSpec
    attachments: tuple[Attachment, ...]


class AgentStepLimit(RuntimeError):
    pass


class ToolExecutionError(RuntimeError):
    pass


class SovereignAgent:
    """Central controller that applies local policy before delegating work."""

    def __init__(
        self,
        config: SovereignConfig,
        executor: BackendExecutor | None = None,
        native_tools: NativeToolRuntime | None = None,
    ):
        self.config = config
        self.policy = PermissionPolicy(config)
        self.attachments = AttachmentInspector(self.policy, config.max_attachment_bytes)
        self.mesh = ComputeMesh(config.backends)
        self.mcp = MCPHub(config.mcp_servers)
        self.executor = executor or BackendExecutor()
        self.native_tools = native_tools or NativeToolRuntime(config, self.policy)

    def plan_route(
        self,
        capability: Capability,
        attachment_paths: Iterable[Path | str] = (),
    ) -> RouteDecision:
        inspected = tuple(self.attachments.inspect(path) for path in attachment_paths)
        if any(item.media_type.startswith("image/") for item in inspected) and capability is Capability.REASONING:
            if self.mesh.candidates(Capability.VISION):
                capability = Capability.VISION
        backend = self.mesh.route(capability)
        return RouteDecision(capability=capability, backend=backend, attachments=inspected)

    def _user_content(self, prompt: str, attachments: tuple[Attachment, ...]) -> str | list[dict[str, Any]]:
        if not attachments:
            return prompt
        blocks: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for attachment in attachments:
            if attachment.media_type.startswith("image/"):
                if attachment.size > self.config.max_inline_image_bytes:
                    raise AttachmentError(
                        f"image {attachment.path.name!r} exceeds inline limit of {self.config.max_inline_image_bytes} bytes"
                    )
                encoded = base64.b64encode(attachment.path.read_bytes()).decode("ascii")
                blocks.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{attachment.media_type};base64,{encoded}"},
                    }
                )
            else:
                blocks.append(
                    {
                        "type": "text",
                        "text": (
                            f"[attachment: {attachment.path.name}; type={attachment.media_type}; "
                            f"size={attachment.size}; sha256={attachment.sha256}]"
                        ),
                    }
                )
        return blocks

    async def _complete_with_failover(
        self,
        capability: Capability,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> tuple[BackendReply, BackendSpec]:
        failures: list[str] = []
        for backend in self.mesh.candidates(capability):
            try:
                reply = await self.executor.complete(backend, messages, tools, capability)
            except BackendExecutionError as exc:
                self.mesh.set_health(backend.name, False)
                failures.append(str(exc))
                continue
            return reply, backend
        if failures:
            raise BackendExecutionError("all candidate backends failed: " + " | ".join(failures))
        raise NoBackendAvailable(f"no healthy backend provides {capability.value}")

    @staticmethod
    def _assistant_tool_message(reply: BackendReply) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": reply.text or None,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, separators=(",", ":")),
                    },
                }
                for call in reply.tool_calls
            ],
        }

    async def run(
        self,
        prompt: str,
        capability: Capability = Capability.REASONING,
        attachment_paths: Iterable[Path | str] = (),
        max_steps: int | None = None,
        approved_tools: Iterable[str] = (),
    ) -> RunResult:
        if not prompt.strip():
            raise ValueError("prompt cannot be empty")
        step_limit = max_steps if max_steps is not None else self.config.max_agent_steps
        if step_limit < 1:
            raise ValueError("max_steps must be at least 1")
        decision = self.plan_route(capability, attachment_paths)
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": self._user_content(prompt, decision.attachments)}
        ]
        clients: dict[str, Any] = {}
        mcp_registry: dict[str, tuple[str, str]] = {}
        native_names = set(self.native_tools.names())
        tools: list[dict[str, Any]] = list(self.native_tools.definitions())
        total_tool_calls = 0
        last_backend = decision.backend.name
        try:
            if self.mcp.names():
                clients, mcp_tools, mcp_registry = await self.mcp.connect_tools()
                collision = native_names.intersection(mcp_registry)
                if collision:
                    raise ToolExecutionError(
                        "tool name collision: " + ", ".join(sorted(collision))
                    )
                tools.extend(mcp_tools)

            for step in range(1, step_limit + 1):
                reply, backend = await self._complete_with_failover(decision.capability, messages, tools)
                last_backend = backend.name
                if not reply.tool_calls:
                    return RunResult(
                        text=reply.text,
                        backend=backend.name,
                        capability=decision.capability,
                        steps=step,
                        tool_calls=total_tool_calls,
                    )

                messages.append(self._assistant_tool_message(reply))

                for call in reply.tool_calls:
                    if call.name in native_names:
                        result = await self.native_tools.execute(
                            call.name,
                            call.arguments,
                            approved_tools,
                        )
                    else:
                        target = mcp_registry.get(call.name)
                        if target is None:
                            raise ToolExecutionError(
                                f"backend requested unknown or unauthorized tool: {call.name}"
                            )
                        server_name, tool_name = target
                        result = await clients[server_name].call_tool(tool_name, call.arguments)
                    total_tool_calls += 1
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": call.name,
                            "content": json.dumps(result, separators=(",", ":"), ensure_ascii=False),
                        }
                    )
            raise AgentStepLimit(
                f"agent reached the {step_limit}-step limit after {total_tool_calls} tool calls; "
                f"last backend={last_backend}"
            )
        finally:
            if clients:
                await asyncio.gather(*(client.close() for client in clients.values()), return_exceptions=True)

    async def run_visual(
        self,
        prompt: str,
        approved_tools: Iterable[str] = (),
        max_steps: int | None = None,
    ) -> VisualRunResult:
        if not prompt.strip():
            raise ValueError("prompt cannot be empty")
        if not self.config.computer_control_enabled:
            raise PermissionError("computer control is disabled")
        if not self.config.visual_autonomy_enabled:
            raise PermissionError("visual autonomy is disabled")
        if not self.mesh.candidates(Capability.VISION):
            raise NoBackendAvailable("visual autonomy requires a healthy vision backend")

        action_tools = self.native_tools.visual_action_definitions()
        action_names = set(self.native_tools.visual_action_names())
        if not action_tools or not action_names:
            raise ToolExecutionError("no visual computer action tools are enabled")

        step_limit = max_steps if max_steps is not None else self.config.max_visual_steps
        if step_limit < 1:
            raise ValueError("max_steps must be at least 1")
        if min(
            self.config.visual_capture_retries,
            self.config.visual_backend_retries,
            self.config.max_visual_recoveries,
        ) < 0 or self.config.visual_retry_delay_seconds < 0:
            raise ValueError("visual retry and recovery settings cannot be negative")

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are operating a desktop through Sovereign. "
                    "Use at most one supplied computer action tool per turn. "
                    "After each action Sovereign will capture and send a fresh screenshot. "
                    "Choose coordinates only from the current screenshot. "
                    "When the task is complete, reply with the final result and make no tool call. "
                    "Never claim an action succeeded until its tool result confirms it."
                ),
            }
        ]

        approvals = tuple(approved_tools)
        total_tool_calls = 0
        last_backend = ""
        recoveries = 0

        for frame in range(1, step_limit + 1):
            screenshot, attachment = await self._capture_visual_frame()

            screen_prompt = (
                f"Task: {prompt}\n"
                f"Current screen frame: {frame}. "
                f"Resolution: {screenshot.get('width', '?')}x{screenshot.get('height', '?')}. "
                f"Frame SHA-256: {attachment.sha256}. "
                "Inspect this fresh screenshot. If the task is complete, answer without a tool call. "
                "Verify the previous action against this frame before choosing another action. "
                "Otherwise choose exactly one approved desktop action."
            )
            messages.append(
                {
                    "role": "user",
                    "content": self._user_content(screen_prompt, (attachment,)),
                }
            )

            reply, backend = await self._complete_visual_with_retries(messages, action_tools)
            last_backend = backend.name

            if not reply.tool_calls:
                return VisualRunResult(
                    text=reply.text,
                    backend=backend.name,
                    frames=frame,
                    tool_calls=total_tool_calls,
                )

            if len(reply.tool_calls) != 1:
                raise ToolExecutionError(
                    "visual autonomy allows exactly one desktop action per screenshot"
                )

            call = reply.tool_calls[0]
            if call.name not in action_names:
                raise ToolExecutionError(
                    f"vision backend requested non-visual or unauthorized tool: {call.name}"
                )
            if frame == step_limit:
                raise AgentStepLimit(
                    f"visual agent reached the {step_limit}-frame limit before an action "
                    "could be verified against a fresh screenshot"
                )

            messages.append(self._assistant_tool_message(reply))
            total_tool_calls += 1
            try:
                result = await self.native_tools.execute(
                    call.name,
                    call.arguments,
                    approvals,
                )
            except PermissionError:
                raise
            except (NativeToolError, ValueError, TypeError, KeyError, OSError) as exc:
                recoveries += 1
                if recoveries > self.config.max_visual_recoveries:
                    raise ToolExecutionError(
                        f"visual action failed {recoveries} times; last error: {exc}"
                    ) from exc
                result = {"ok": False, "error": str(exc)}
            else:
                recoveries = 0
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.name,
                    "content": json.dumps(result, separators=(",", ":"), ensure_ascii=False),
                }
            )

            delay = max(float(self.config.visual_action_delay_seconds), 0.0)
            if delay:
                await asyncio.sleep(delay)

        raise AgentStepLimit(
            f"visual agent reached the {step_limit}-frame limit after "
            f"{total_tool_calls} actions; last backend={last_backend}"
        )

    async def _capture_visual_frame(self) -> tuple[dict[str, Any], Attachment]:
        for attempt in range(self.config.visual_capture_retries + 1):
            try:
                screenshot = await self.native_tools.capture_screen()
                screenshot_path = screenshot.get("path")
                if not screenshot_path:
                    raise ToolExecutionError("screen capture did not return a path")
                attachment = self.attachments.inspect(str(screenshot_path))
                if not attachment.media_type.startswith("image/"):
                    raise ToolExecutionError("screen capture is not an image")
                return screenshot, attachment
            except PermissionError:
                raise
            except (NativeToolError, OSError, AttachmentError, ToolExecutionError) as exc:
                if attempt == self.config.visual_capture_retries:
                    raise ToolExecutionError(
                        f"screen capture failed after {attempt + 1} attempts: {exc}"
                    ) from exc
                await asyncio.sleep(self.config.visual_retry_delay_seconds * (2**attempt))
        raise AssertionError("unreachable")

    async def _complete_visual_with_retries(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> tuple[BackendReply, BackendSpec]:
        failures: list[str] = []
        candidates = self.mesh.candidates(Capability.VISION)
        for backend in candidates:
            for attempt in range(self.config.visual_backend_retries + 1):
                try:
                    return await self.executor.complete(backend, messages, tools, Capability.VISION), backend
                except BackendExecutionError as exc:
                    if attempt == self.config.visual_backend_retries:
                        failures.append(f"{backend.name}: {exc}")
                    else:
                        await asyncio.sleep(self.config.visual_retry_delay_seconds * (2**attempt))
        if failures:
            raise BackendExecutionError("all vision backends failed: " + " | ".join(failures))
        raise NoBackendAvailable("visual autonomy requires a healthy vision backend")

    def status(self) -> dict[str, object]:
        return {
            "version": __version__,
            "controller": "sovereign",
            "permission_mode": self.config.permission_mode.value,
            "workspace": str(self.config.workspace.expanduser()),
            "backends": self.mesh.status(),
            "mcp_servers": self.mcp.names(),
            "native_tools": self.native_tools.names(),
            "computer_control_enabled": self.config.computer_control_enabled,
            "visual_autonomy_enabled": self.config.visual_autonomy_enabled,
            "filesystem_write_enabled": self.config.filesystem_write_enabled,
        }
