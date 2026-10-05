# Sovereign v6.7

Sovereign is a local-first AI agent controller. v6.7 adds real backend execution and an autonomous MCP tool loop while keeping all routing and permissions under Sovereign's control.

## v6.7 execution milestone

- Executes requests against OpenAI-compatible or Sovereign-native JSON backends.
- Automatic failover across healthy backends that provide the requested capability.
- Discovers MCP stdio tools, exposes them to the selected model, executes requested calls, and feeds results back to the model.
- Namespaces MCP tools per server to avoid ambiguous tool names.
- Sends the MCP initialized notification after handshake.
- Supports prompt execution from the CLI and local HTTP API.
- Keeps sandbox / selected-root / explicit full-access path policy in front of attachment access.
- Supports inline image attachments for compatible vision backends, with a configurable size limit.
- Environment-backed secrets remain local and are resolved only when a backend call is made.

## Install

    python -m pip install -e .
    sovereign doctor

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

Local API endpoints:

- `GET /health`
- `GET /v1/status`
- `POST /v1/route`
- `POST /v1/run`

## Permission model

- `sandbox`: Sovereign workspace only.
- `selected`: workspace plus explicitly selected roots.
- `full`: unrestricted path checks only when `full_access_opt_in=true`.

Remote model output is never treated as permission to bypass the local policy.

Current version: 6.7.0.
