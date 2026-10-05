# Sovereign v6.6

Sovereign is a local-first AI agent controller. v6.6 keeps Sovereign in charge while routing work to local, hosted, or explicitly authorized reasoning backends and MCP tools.

## v6.6 integration foundation

- Sovereign remains the controller; providers are workers.
- Capability-aware Compute Mesh for reasoning, vision, image generation, video generation, and tools.
- Permission-gated computer access with sandbox, selected-root, and explicit full-access modes.
- File/media attachment validation with size limits and SHA-256 fingerprints.
- MCP stdio JSON-RPC connections with initialize, tool discovery, and tool calls.
- Environment-backed secrets for provider headers.
- Local HTTP API plus CLI.
- Deterministic tests and GitHub Actions CI.

## Install

    python -m pip install -e .
    sovereign doctor

## Run

    sovereign status
    sovereign route reasoning
    sovereign serve --port 8765

Local API endpoints: GET /health, GET /v1/status, POST /v1/route.

## Permission model

- sandbox: Sovereign workspace only.
- selected: workspace plus explicitly selected roots.
- full: unrestricted path checks only when full_access_opt_in=true.

Remote model output is never treated as permission to bypass the local policy.

Current version: 6.6.0.