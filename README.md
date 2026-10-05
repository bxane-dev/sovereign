# Sovereign v8.0

Sovereign is a local-first AI agent controller with a Python execution core, a Bun/TypeScript terminal client, and an Electron desktop shell for Windows, macOS, and Linux.

## Desktop app

The desktop shell starts its bundled Python core on a random loopback port with a per-launch bearer token. Its isolated renderer accesses only selected core endpoints through Electron IPC. The app offers persistent reasoning conversations, per-run action approvals, desktop vision tasks, and update checks against GitHub Releases.

Development run:

    python -m pip install -e ".[desktop,dev]"
    pnpm install --frozen-lockfile
    pnpm --filter @sovereign/desktop run start

Build an installer for the current operating system:

    python -m pip install -e ".[desktop,build]"
    python scripts/build_core.py
    python scripts/smoke_core.py
    python scripts/build_terminal.py
    pnpm --filter @sovereign/desktop run dist

Release builds use the locked `uv.lock` and `pnpm-lock.yaml` dependency graphs. See [docs/RELEASE.md](docs/RELEASE.md) for signing, notarization, and release steps.

## Persistent sessions

Reasoning conversations are checkpointed in `workspace/sessions.sqlite3`. Create a session with `sovereign session new` or `POST /v1/sessions`, then pass its ID to `sovereign run --session ID` or the `/v1/run` API. Use `sovereign session list`, `show`, and `resume` to inspect or continue work. If the process stops after requesting a tool but before recording its result, resumption reports an unknown outcome to the model and does not replay the action. Delete a session with `DELETE /v1/sessions/{id}`.

## Backends

Configured backends may use `openai` (OpenAI-compatible chat completions), `ollama` (native `/api/chat`), `anthropic` (Messages API), or `sovereign` protocol. Declare the capabilities a model actually supports; visual autonomy requires `vision` and tool calling. API keys should be referenced through `env:` header values or `ANTHROPIC_API_KEY`, and are never written into the config file.

Example local Ollama backend:

    {"name":"ollama","endpoint":"http://127.0.0.1:11434/api/chat","protocol":"ollama","model":"your-vision-model","capabilities":["reasoning","vision"]}

Example Anthropic backend:

    {"name":"claude","endpoint":"https://api.anthropic.com/v1/messages","protocol":"anthropic","model":"your-model","capabilities":["reasoning","vision"],"headers":{"x-api-key":"env:ANTHROPIC_API_KEY"}}

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
Every frame carries a SHA-256 identifier. The next model turn receives the previous action result and a new image so it can verify what changed. If an action fails, Sovereign reports the error to the model and captures a fresh frame before another decision. Permission denials stop the run immediately.

Screen capture and vision backend requests have bounded retries. Backend exhaustion falls through to the next healthy vision backend; a transient failure does not permanently remove a backend from later runs. Desktop actions are never automatically retried because a failed call may have partially changed the UI. The final frame is reserved for verification, so Sovereign will not execute an action that cannot be checked with another screenshot.

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

    pnpm install --frozen-lockfile
    pnpm --filter @sovereign/terminal run start

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
      "visual_capture_retries": 2,
      "visual_backend_retries": 2,
      "visual_retry_delay_seconds": 0.25,
      "max_visual_recoveries": 2,
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
- `POST /v1/sessions`, `GET /v1/sessions`, `GET /v1/sessions/{id}`
- `POST /v1/sessions/{id}/resume`, `DELETE /v1/sessions/{id}`
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
Configured MCP tools also require exact per-run approval before Sovereign exposes or executes them. Binding the API beyond loopback requires `SOVEREIGN_API_TOKEN`.

## Verification

Run `python -m pytest` for the control plane and visual loop tests. CI runs the Python tests on Linux, Windows, and macOS, and runs the Bun terminal type check and tests on Linux. The visual tests use a simulated desktop and backend; a live vision backend and desktop integration still require a manual smoke run in the target environment.

When `SOVEREIGN_API_TOKEN` is set, every API route requires `Authorization: Bearer <token>`. The packaged desktop app sets a fresh token for its own core process.

Current version: 8.0.0.
