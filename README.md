# Sovereign v7.0

Sovereign is a local-first AI agent controller with a trusted Python execution core and a modern terminal client.

## v7.0 terminal architecture

v7.0 adds a Claude Code-style **application stack** for the terminal experience:

- **TypeScript** — terminal/client implementation
- **React** — component model
- **Ink** — React rendering in the terminal
- **Yoga** — terminal layout calculations
- **Bun** — runtime, package management, tests, and development tooling

This is an architectural/library alignment only. Sovereign does not copy or depend on proprietary Claude Code source.

The trusted execution core remains:

- Python
- FastAPI
- Pydantic
- asyncio
- official OpenAI Python SDK
- MCP
- permission-gated native filesystem and computer tools
- pytest
- optional PyTorch support for local ML work

## Architecture

    apps/terminal (Bun + TypeScript + React + Ink + Yoga)
                |
                | HTTP on localhost
                v
    FastAPI control plane
                |
                v
    Sovereign agent / Compute Mesh / MCP / native tools
                |
        permission + approval gates
                |
                v
    filesystem / screen / mouse / keyboard / model backends

The terminal UI never bypasses the Python permission layer.

## Install the core

    python -m pip install -e ".[dev]"

For desktop control:

    python -m pip install -e ".[desktop]"

Start the local control plane:

    sovereign serve --port 8765

## Install the terminal client

Install Bun, then:

    cd apps/terminal
    bun install
    bun run start

The client connects to:

    http://127.0.0.1:8765

Override it with:

    SOVEREIGN_API_URL=http://127.0.0.1:9000 bun run start

## Terminal commands

- `/status` — controller, permissions, workspace, and control status
- `/tools` — enabled native tools and MCP servers
- `/approve <tool>` — approve one gated tool for the **next prompt only**
- `/revoke <tool>` — remove a pending next-run approval
- `/clear` — clear the visible transcript
- `/help` — show commands
- `/quit` — exit

Example:

    /approve sovereign__mouse_click
    /approve sovereign__type_text
    Open the editor and type hello

Those approvals are sent only with that run and are cleared afterwards.

## Native tools

Read-only filesystem tools obey Sovereign's path policy.

Optional write and computer-control tools include:

- `sovereign__write_text`
- `sovereign__screen_size`
- `sovereign__screenshot`
- `sovereign__mouse_move`
- `sovereign__mouse_click`
- `sovereign__type_text`
- `sovereign__press_key`
- `sovereign__hotkey`

Computer control defaults off. Filesystem writes default off. Mutating/input actions require explicit run approval.

## FastAPI

Endpoints:

- `GET /health`
- `GET /v1/status`
- `GET /v1/tools`
- `POST /v1/route`
- `POST /v1/run`
- `/docs` for interactive OpenAPI documentation

## Tests

Python:

    python -m pytest

Terminal:

    cd apps/terminal
    bun run check
    bun test

GitHub Actions validates Python 3.11–3.13 and the Bun/TypeScript terminal client.

## Permission model

- `sandbox`: Sovereign workspace only
- `selected`: workspace plus explicitly selected roots
- `full`: unrestricted path checks only when `full_access_opt_in=true`

Remote model output and terminal-client input are never treated as permission to bypass local policy or approval gates.

Current version: 7.0.0.
