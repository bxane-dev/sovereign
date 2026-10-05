from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping


class Capability(str, Enum):
    REASONING = "reasoning"
    VISION = "vision"
    IMAGE_GENERATION = "image_generation"
    VIDEO_GENERATION = "video_generation"
    TOOLS = "tools"


class PermissionMode(str, Enum):
    SANDBOX = "sandbox"
    SELECTED = "selected"
    FULL = "full"


@dataclass(frozen=True, slots=True)
class BackendSpec:
    name: str
    endpoint: str
    capabilities: frozenset[Capability]
    priority: int = 0
    timeout_seconds: float = 60.0
    headers: Mapping[str, str] = field(default_factory=dict)
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "BackendSpec":
        name = str(data["name"]).strip()
        endpoint = str(data["endpoint"]).strip()
        if not name or not endpoint:
            raise ValueError("backend name and endpoint are required")
        raw_caps = data.get("capabilities", [])
        if not isinstance(raw_caps, list) or not raw_caps:
            raise ValueError(f"backend {name!r} must declare at least one capability")
        caps = frozenset(Capability(str(item)) for item in raw_caps)
        headers = data.get("headers", {})
        if not isinstance(headers, dict):
            raise ValueError("backend headers must be an object")
        return cls(
            name=name,
            endpoint=endpoint,
            capabilities=caps,
            priority=int(data.get("priority", 0)),
            timeout_seconds=float(data.get("timeout_seconds", 60.0)),
            headers={str(k): str(v) for k, v in headers.items()},
            enabled=bool(data.get("enabled", True)),
        )


@dataclass(frozen=True, slots=True)
class MCPServerSpec:
    name: str
    command: tuple[str, ...]
    env: Mapping[str, str] = field(default_factory=dict)
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "MCPServerSpec":
        name = str(data["name"]).strip()
        command = data.get("command", [])
        if not isinstance(command, list) or not command:
            raise ValueError(f"MCP server {name!r} requires a command array")
        env = data.get("env", {})
        if not isinstance(env, dict):
            raise ValueError("MCP env must be an object")
        return cls(
            name=name,
            command=tuple(str(part) for part in command),
            env={str(k): str(v) for k, v in env.items()},
            enabled=bool(data.get("enabled", True)),
        )


@dataclass(frozen=True, slots=True)
class Attachment:
    path: Path
    media_type: str
    size: int
    sha256: str
