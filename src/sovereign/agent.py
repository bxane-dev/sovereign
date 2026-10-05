from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .attachments import AttachmentInspector
from .config import SovereignConfig
from .mcp import MCPHub
from .mesh import ComputeMesh
from .models import Attachment, BackendSpec, Capability
from .permissions import PermissionPolicy


@dataclass(frozen=True, slots=True)
class RouteDecision:
    capability: Capability
    backend: BackendSpec
    attachments: tuple[Attachment, ...]


class SovereignAgent:
    """Central controller that applies local policy before delegating work."""

    def __init__(self, config: SovereignConfig):
        self.config = config
        self.policy = PermissionPolicy(config)
        self.attachments = AttachmentInspector(self.policy, config.max_attachment_bytes)
        self.mesh = ComputeMesh(config.backends)
        self.mcp = MCPHub(config.mcp_servers)

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

    def status(self) -> dict[str, object]:
        return {
            "version": "6.6.0",
            "controller": "sovereign",
            "permission_mode": self.config.permission_mode.value,
            "workspace": str(self.config.workspace.expanduser()),
            "backends": self.mesh.status(),
            "mcp_servers": self.mcp.names(),
        }
