from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .attachments import AttachmentError, AttachmentInspector
from .backend import BackendExecutionError, BackendExecutor
from .config import SovereignConfig
from .mcp import MCPHub
from .mesh import ComputeMesh, NoBackendAvailable
from .models import Attachment, BackendReply, BackendSpec, Capability, RunResult
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

    def __init__(self, config: SovereignConfig, executor: BackendExecutor | None = None):
        self.config = config
        self.policy = PermissionPolicy(config)
        self.attachments = AttachmentInspector(self.policy, config.max_attachment_bytes)
        self.mesh = ComputeMesh(config.backends)
        self.mcp = MCPHub(config.mcp_servers)
        self.executor = executor or BackendExecutor()

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

    async def run(
        self,
        prompt: str,
        capability: Capability = Capability.REASONING,
        attachment_paths: Iterable[Path | str] = (),
        max_steps: int | None = None,
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
        tools: list[dict[str, Any]] = []
        registry: dict[str, tuple[str, str]] = {}
        total_tool_calls = 0
        last_backend = decision.backend.name
        try:
            if self.mcp.names():
                clients, tools, registry = await self.mcp.connect_tools()
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

                assistant_tool_calls = []
                for call in reply.tool_calls:
                    assistant_tool_calls.append(
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments, separators=(",", ":")),
                            },
                        }
                    )
                messages.append(
                    {
                        "role": "assistant",
                        "content": reply.text or None,
                        "tool_calls": assistant_tool_calls,
                    }
                )

                for call in reply.tool_calls:
                    target = registry.get(call.name)
                    if target is None:
                        raise ToolExecutionError(f"backend requested unknown or unauthorized tool: {call.name}")
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
                f"agent reached the {step_limit}-step limit after {total_tool_calls} tool calls; last backend={last_backend}"
            )
        finally:
            if clients:
                await asyncio.gather(*(client.close() for client in clients.values()), return_exceptions=True)

    def status(self) -> dict[str, object]:
        return {
            "version": "6.7.0",
            "controller": "sovereign",
            "permission_mode": self.config.permission_mode.value,
            "workspace": str(self.config.workspace.expanduser()),
            "backends": self.mesh.status(),
            "mcp_servers": self.mcp.names(),
        }
