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
    max_inline_image_bytes: int = 8 * 1024 * 1024
    max_agent_steps: int = 8
    native_tools_enabled: bool = True
    filesystem_write_enabled: bool = False
    computer_control_enabled: bool = False
    visual_autonomy_enabled: bool = False
    max_visual_steps: int = 12
    visual_action_delay_seconds: float = 0.35
    max_native_read_chars: int = 200_000
    max_native_write_chars: int = 1_000_000
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
            max_inline_image_bytes=int(data.get("max_inline_image_bytes", 8 * 1024 * 1024)),
            max_agent_steps=int(data.get("max_agent_steps", 8)),
            native_tools_enabled=bool(data.get("native_tools_enabled", True)),
            filesystem_write_enabled=bool(data.get("filesystem_write_enabled", False)),
            computer_control_enabled=bool(data.get("computer_control_enabled", False)),
            visual_autonomy_enabled=bool(data.get("visual_autonomy_enabled", False)),
            max_visual_steps=int(data.get("max_visual_steps", 12)),
            visual_action_delay_seconds=float(data.get("visual_action_delay_seconds", 0.35)),
            max_native_read_chars=int(data.get("max_native_read_chars", 200_000)),
            max_native_write_chars=int(data.get("max_native_write_chars", 1_000_000)),
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
