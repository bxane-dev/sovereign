from pathlib import Path

from sovereign.config import SovereignConfig
from sovereign.models import Capability, PermissionMode


def test_config_parses_backends_and_mcp():
    cfg = SovereignConfig.from_dict(
        {
            "permission_mode": "selected",
            "workspace": "~/sv",
            "allowed_roots": ["~/code"],
            "backends": [
                {
                    "name": "reasoner",
                    "endpoint": "http://127.0.0.1:1",
                    "protocol": "openai",
                    "model": "demo",
                    "capabilities": ["reasoning", "vision"],
                    "priority": 9,
                }
            ],
            "mcp_servers": [{"name": "tools", "command": ["python", "server.py"]}],
        }
    )
    assert cfg.permission_mode is PermissionMode.SELECTED
    assert cfg.workspace == Path("~/sv").expanduser()
    assert cfg.backends[0].capabilities == frozenset({Capability.REASONING, Capability.VISION})
    assert cfg.backends[0].model == "demo"
    assert cfg.mcp_servers[0].command == ("python", "server.py")
