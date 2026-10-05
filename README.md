# Sovereign v7.1

Sovereign is a local-first AI agent controller with a trusted Python execution core and a Bun/TypeScript terminal client.

## v7.1 visual computer autonomy

v7.1 adds a screenshot-driven computer loop:

1. Sovereign captures a fresh desktop screenshot.
2. The screenshot is sent to a healthy vision-capable backend.
3. The model may request exactly **one** desktop action from the allowed visual tools.
4. Sovereign checks the per-run approval for that exact tool.
5. The action runs locally.
6. Sovereign waits briefly for the UI to settle, captures a new screenshot, and reasons again.
7. The loop stops when the model returns a final answer without a tool call or the frame limit is reached.

This prevents a model from executing a long chain of clicks against an old screenshot.

## Required opt-ins

Visual autonomy has two independent local gates:

    {
      "computer_control_enabled": true,
      "visual_autonomy_enabled": true
    }

It also requires at least one configured backend with the `vision` capability.

State-changing computer actions still need explicit per-run approvals, for example:

    sovereign computer "Open the editor and type hello" \
      --approve-tool sovereign__mouse_click \
      --approve-tool sovereign__type_text

No approval is inferred from model output.

## Terminal client

The terminal application uses:

- TypeScript
- React
- Ink
- Yoga
- Bun

Start the Python control plane:

    python -m pip install -e ".[desktop,dev]"
    sovereign serve --port 8765

Start the terminal:

    cd apps/terminal
    bun install
    bun run start

Then approve exact actions for the next run and use `/visual`:

    /approve sovereign__mouse_click
    /approve sovereign__type_text
    /visual Open the editor and type hello

Pending approvals are cleared after that run.

## Visual action tools

The vision loop can choose only from enabled desktop action tools:

- `sovereign__mouse_move`
- `sovereign__mouse_click`
- `sovereign__type_text`
- `sovereign__press_key`
- `sovereign__hotkey`

Screenshots are captured automatically by Sovereign and are not a model-selected action inside the visual loop.

## Configuration

Example `~/.sovereign/config.json`:

    {
      "permission_mode": "sandbox",
      "workspace": "~/.sovereign/workspace",
      "computer_control_enabled": true,
      "visual_autonomy_enabled": true,
      "max_visual_steps": 12,
      "visual_action_delay_seconds": 0.35,
      "backends": [
        {
          "name": "vision-model",
          "endpoint": "http://127.0.0.1:11434/v1/chat/completions",
          "protocol": "openai",
          "model": "vision-model",
          "capabilities": ["reasoning", "vision"],
          "priority": 100
        }
      ]
    }

## API

FastAPI endpoints include:

- `GET /health`
- `GET /v1/status`
- `GET /v1/tools`
- `POST /v1/route`
- `POST /v1/run`
- `POST /v1/computer/run`
- `/docs` for interactive OpenAPI documentation

Example computer request:

    {
      "prompt": "Open settings",
      "approved_tools": [
        "sovereign__mouse_click"
      ],
      "max_steps": 8
    }

## Core architecture

    Bun + TypeScript + React + Ink + Yoga terminal
                     |
                     v
                FastAPI
                     |
                     v
             Sovereign agent
              /           \
      Compute Mesh       MCP tools
              |
        vision backend
              |
      screenshot -> one approved action -> screenshot
              |
      local permission + approval gates
              |
       screen / mouse / keyboard / filesystem

## Install

Core development:

    python -m pip install -e ".[dev]"

Desktop support:

    python -m pip install -e ".[desktop]"

Optional local ML support:

    python -m pip install -e ".[ml]"

## Permission model

- `sandbox`: Sovereign workspace only
- `selected`: workspace plus explicitly selected roots
- `full`: unrestricted path checks only when `full_access_opt_in=true`

Computer control defaults off. Visual autonomy defaults off. Filesystem writes default off. Remote model output and terminal input never bypass these local gates.

Current version: 7.1.0.
