# Sovereign v6.8

Sovereign is a local-first AI agent controller. v6.8 moves the control-plane architecture onto FastAPI, Pydantic, asyncio, and the official OpenAI Python SDK while preserving Sovereign's permission system, compute mesh, and MCP tool loop.

## v6.8 stack alignment

- Python remains the primary orchestration language.
- FastAPI provides the local HTTP/API control plane and OpenAPI schema.
- Pydantic validates request and response structures.
- asyncio drives backend calls and autonomous MCP tool execution.
- The official OpenAI Python SDK handles OpenAI-compatible chat-completions backends asynchronously.
- pytest remains the automated test framework.
- PyTorch is available as the optional `ml` extra for future local model/runtime components instead of being forced onto lightweight controller installs.

## Install

    python -m pip install -e .
    sovereign doctor

Development install:

    python -m pip install -e ".[dev]"

Optional local ML runtime:

    python -m pip install -e ".[ml]"

## Configure

Example `~/.sovereign/config.json`:

    {
      "permission_mode": "sandbox",
      "backends": [
        {
          "name": "local-model",
          "endpoint": "http://127.0.0.1:11434/v1/chat/completions",
          "protocol": "openai",
          "model": "local-model",
          "capabilities": ["reasoning", "vision"],
          "priority": 100
        }
      ],
      "mcp_servers": [
        {
          "name": "local-tools",
          "command": ["python", "my_mcp_server.py"]
        }
      ]
    }

Headers can reference environment variables, for example `"Authorization": "env:SOVEREIGN_API_KEY"`.

## Run

    sovereign status
    sovereign route reasoning
    sovereign run "Inspect the project and summarize the failing tests"
    sovereign serve --port 8765

FastAPI exposes:

- `GET /health`
- `GET /v1/status`
- `POST /v1/route`
- `POST /v1/run`
- interactive OpenAPI docs at `/docs`

## Permission model

- `sandbox`: Sovereign workspace only.
- `selected`: workspace plus explicitly selected roots.
- `full`: unrestricted path checks only when `full_access_opt_in=true`.

Remote model output is never treated as permission to bypass the local policy.

Current version: 6.8.0.
