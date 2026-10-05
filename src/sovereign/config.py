from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import BackendSpec, MCPServerSpec, PermissionMode


DEFAULT_CONFIG = Path.home() / ".sovereign" / "config.json"
DEFAULT_WORKSPACE = Path.home() / ".sovereign" / "workspace"


@dataclass(slots=True)
class SovereignConfig:
    permission_mode: PermissionMode = PermissionMode.SANDBOX
    workspace: Path = DEFAULT_WORKSPACE
    allowed_roots: list[Path] = field(default_factory=list)
    full_access_opt_in: bool = False
    max_attachment_bytes: int = 128 * 1024 * 1024
    backends: list[BackendSpec] = field(default_factory=list)
    mcp_servers: list[MCPServerSpec] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SovereignConfig":
        workspace = Path(str(data.get("workspace", DEFAULT_WORKSPACE))).expanduser()
        roots = [Path(str(p)).expanduser() for p in data.get("allowed_roots", [])]
        return cls(
            permission_mode=PermissionMode(str(data.get("permission_mode", "sandbox"))),
            workspace=workspace,
            allowed_roots=roots,
            full_access_opt_in=bool(data.get("full_access_opt_in", False)),
            max_attachment_bytes=int(data.get("max_attachment_bytes", 128 * 1024 * 1024)),
            backends=[BackendSpec.from_dict(item) for item in data.get("backends", [])],
            mcp_servers=[MCPServerSpec.from_dict(item) for item in data.get("mcp_servers", [])],
        )


def load_config(path: Path | str | None = None) -> SovereignConfig:
    config_path = Path(path).expanduser() if path else DEFAULT_CONFIG
    if not config_path.exists():
        return SovereignConfig()
    with config_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Sovereign config root must be a JSON object")
    return SovereignConfig.from_dict(payload)
