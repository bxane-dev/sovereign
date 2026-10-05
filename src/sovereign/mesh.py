from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable

from .models import BackendSpec, Capability


class NoBackendAvailable(RuntimeError):
    pass


@dataclass(slots=True)
class BackendState:
    spec: BackendSpec
    healthy: bool = True
    consecutive_failures: int = 0


class ComputeMesh:
    """Capability-aware backend registry with deterministic priority routing."""

    def __init__(self, backends: Iterable[BackendSpec] = ()):
        self._states = {spec.name: BackendState(spec) for spec in backends}

    def register(self, spec: BackendSpec) -> None:
        self._states[spec.name] = BackendState(spec)

    def set_health(self, name: str, healthy: bool) -> None:
        state = self._states[name]
        state.healthy = healthy
        state.consecutive_failures = 0 if healthy else state.consecutive_failures + 1

    def candidates(self, capability: Capability) -> list[BackendSpec]:
        specs = [
            state.spec
            for state in self._states.values()
            if state.healthy and state.spec.enabled and capability in state.spec.capabilities
        ]
        return sorted(specs, key=lambda item: (-item.priority, item.name))

    def route(self, capability: Capability) -> BackendSpec:
        candidates = self.candidates(capability)
        if not candidates:
            raise NoBackendAvailable(f"no healthy backend provides {capability.value}")
        return candidates[0]

    @staticmethod
    def resolved_headers(spec: BackendSpec) -> dict[str, str]:
        headers: dict[str, str] = {}
        for key, value in spec.headers.items():
            if value.startswith("env:"):
                env_name = value[4:]
                env_value = os.getenv(env_name)
                if env_value is None:
                    raise RuntimeError(f"required environment variable is not set: {env_name}")
                headers[key] = env_value
            else:
                headers[key] = value
        return headers

    def status(self) -> list[dict[str, object]]:
        return [
            {
                "name": state.spec.name,
                "healthy": state.healthy,
                "enabled": state.spec.enabled,
                "priority": state.spec.priority,
                "capabilities": sorted(cap.value for cap in state.spec.capabilities),
            }
            for state in sorted(self._states.values(), key=lambda item: item.spec.name)
        ]
