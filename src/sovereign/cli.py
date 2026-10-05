from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys
from pathlib import Path

from . import __version__
from .agent import SovereignAgent
from .api import serve
from .config import load_config
from .models import Capability


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sovereign", description="Sovereign local-first agent controller")
    parser.add_argument("--config", type=Path, help="path to config.json")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="check local runtime and config")
    sub.add_parser("status", help="print controller status")
    route = sub.add_parser("route", help="show which backend would receive a capability")
    route.add_argument("capability", choices=[cap.value for cap in Capability])
    run = sub.add_parser("run", help="execute a prompt through Sovereign")
    run.add_argument("prompt")
    run.add_argument("--capability", choices=[cap.value for cap in Capability], default="reasoning")
    run.add_argument("--attach", action="append", default=[], type=Path)
    run.add_argument("--max-steps", type=int)
    server = sub.add_parser("serve", help="run the local HTTP API")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8765)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = load_config(args.config)
    agent = SovereignAgent(config)

    if args.command == "doctor":
        report = {
            "ok": True,
            "version": __version__,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "permission_mode": config.permission_mode.value,
            "backends": len(config.backends),
            "mcp_servers": len(config.mcp_servers),
        }
        print(json.dumps(report, indent=2))
        return 0
    if args.command == "status":
        print(json.dumps(agent.status(), indent=2))
        return 0
    if args.command == "route":
        decision = agent.plan_route(Capability(args.capability))
        print(json.dumps({"capability": decision.capability.value, "backend": decision.backend.name}, indent=2))
        return 0
    if args.command == "run":
        result = asyncio.run(
            agent.run(
                args.prompt,
                Capability(args.capability),
                args.attach,
                args.max_steps,
            )
        )
        print(result.text)
        return 0
    if args.command == "serve":
        print(f"Sovereign {__version__} listening on http://{args.host}:{args.port}", file=sys.stderr)
        serve(agent, args.host, args.port)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
