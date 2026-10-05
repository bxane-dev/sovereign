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


def _add_approval_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--approve-tool",
        action="append",
        default=[],
        help="approve one gated native tool for this run; may be repeated",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sovereign", description="Sovereign local-first agent controller")
    parser.add_argument("--config", type=Path, help="path to config.json")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="check local runtime and config")
    sub.add_parser("status", help="print controller status")
    sub.add_parser("tools", help="list enabled native tools and MCP servers")
    route = sub.add_parser("route", help="show which backend would receive a capability")
    route.add_argument("capability", choices=[cap.value for cap in Capability])

    run = sub.add_parser("run", help="execute a prompt through Sovereign")
    run.add_argument("prompt")
    run.add_argument("--capability", choices=[cap.value for cap in Capability], default="reasoning")
    run.add_argument("--attach", action="append", default=[], type=Path)
    run.add_argument("--max-steps", type=int)
    run.add_argument("--session", help="continue a persistent session by ID")
    _add_approval_args(run)

    session = sub.add_parser("session", help="manage persistent agent sessions")
    session_sub = session.add_subparsers(dest="session_command", required=True)
    session_sub.add_parser("new", help="create a reasoning session")
    session_sub.add_parser("list", help="list recent sessions")
    show = session_sub.add_parser("show", help="show a session and its messages")
    show.add_argument("id")
    resume = session_sub.add_parser("resume", help="resume an interrupted task")
    resume.add_argument("id")
    resume.add_argument("--max-steps", type=int)
    _add_approval_args(resume)

    computer = sub.add_parser(
        "computer",
        help="run the screenshot-driven visual computer agent",
    )
    computer.add_argument("prompt")
    computer.add_argument("--max-steps", type=int)
    _add_approval_args(computer)

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
            "native_tools": agent.native_tools.names(),
            "computer_control_enabled": config.computer_control_enabled,
            "visual_autonomy_enabled": config.visual_autonomy_enabled,
            "filesystem_write_enabled": config.filesystem_write_enabled,
        }
        print(json.dumps(report, indent=2))
        return 0
    if args.command == "status":
        print(json.dumps(agent.status(), indent=2))
        return 0
    if args.command == "tools":
        print(
            json.dumps(
                {
                    "native_tools": agent.native_tools.names(),
                    "visual_action_tools": agent.native_tools.visual_action_names(),
                    "mcp_servers": agent.mcp.names(),
                },
                indent=2,
            )
        )
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
                args.approve_tool,
                args.session,
            )
        )
        print(result.text)
        return 0
    if args.command == "session":
        if args.session_command == "new":
            print(json.dumps(agent.sessions.create().summary(), indent=2))
        elif args.session_command == "list":
            print(json.dumps([item.summary() for item in agent.sessions.list()], indent=2))
        elif args.session_command == "show":
            item = agent.sessions.get(args.id)
            print(json.dumps({**item.summary(), "messages": item.messages}, indent=2))
        elif args.session_command == "resume":
            result = asyncio.run(agent.run(
                "", max_steps=args.max_steps, approved_tools=args.approve_tool,
                session_id=args.id, resume=True,
            ))
            print(result.text)
        return 0
    if args.command == "computer":
        result = asyncio.run(
            agent.run_visual(
                args.prompt,
                args.approve_tool,
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
