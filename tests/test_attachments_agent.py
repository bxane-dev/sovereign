from pathlib import Path

from sovereign.agent import SovereignAgent
from sovereign.config import SovereignConfig
from sovereign.models import BackendSpec, Capability


def test_image_attachment_upgrades_reasoning_to_vision(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    image = workspace / "photo.png"
    image.write_bytes(b"not-a-real-png-but-valid-for-routing")
    cfg = SovereignConfig(
        workspace=workspace,
        backends=[
            BackendSpec("text", "http://text", frozenset({Capability.REASONING}), priority=10),
            BackendSpec("vision", "http://vision", frozenset({Capability.VISION}), priority=5),
        ],
    )
    decision = SovereignAgent(cfg).plan_route(Capability.REASONING, [image])
    assert decision.capability is Capability.VISION
    assert decision.backend.name == "vision"
    assert decision.attachments[0].media_type == "image/png"
    assert len(decision.attachments[0].sha256) == 64


def test_reasoning_stays_reasoning_without_vision_backend(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    image = workspace / "photo.png"
    image.write_bytes(b"x")
    cfg = SovereignConfig(
        workspace=workspace,
        backends=[BackendSpec("text", "http://text", frozenset({Capability.REASONING}))],
    )
    decision = SovereignAgent(cfg).plan_route(Capability.REASONING, [image])
    assert decision.capability is Capability.REASONING
