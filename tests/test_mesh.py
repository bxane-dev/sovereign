import pytest

from sovereign.mesh import ComputeMesh, NoBackendAvailable
from sovereign.models import BackendSpec, Capability


def backend(name: str, priority: int, *caps: Capability) -> BackendSpec:
    return BackendSpec(name=name, endpoint=f"http://{name}", capabilities=frozenset(caps), priority=priority)


def test_routes_highest_priority_backend():
    mesh = ComputeMesh([
        backend("slow", 1, Capability.REASONING),
        backend("fast", 10, Capability.REASONING),
    ])
    assert mesh.route(Capability.REASONING).name == "fast"


def test_skips_unhealthy_backend():
    mesh = ComputeMesh([
        backend("a", 10, Capability.REASONING),
        backend("b", 1, Capability.REASONING),
    ])
    mesh.set_health("a", False)
    assert mesh.route(Capability.REASONING).name == "b"


def test_no_backend_for_missing_capability():
    mesh = ComputeMesh([backend("a", 1, Capability.REASONING)])
    with pytest.raises(NoBackendAvailable):
        mesh.route(Capability.VIDEO_GENERATION)


def test_env_header_resolution(monkeypatch):
    spec = BackendSpec(
        name="x",
        endpoint="http://x",
        capabilities=frozenset({Capability.REASONING}),
        headers={"Authorization": "env:TOKEN"},
    )
    monkeypatch.setenv("TOKEN", "secret")
    assert ComputeMesh.resolved_headers(spec) == {"Authorization": "secret"}
