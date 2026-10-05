# Sovereign v6.9

Sovereign is a local-first AI agent controller. v6.9 adds a permission-gated native computer/tool runtime on top of the FastAPI, Pydantic, asyncio, OpenAI SDK, and MCP architecture.

## v6.9 computer runtime

Sovereign now has native tools for:

- reading text files inside permitted filesystem roots
- listing directories inside permitted filesystem roots
- optionally writing text files
- screen-size inspection
- screenshots
- mouse movement and clicks
- keyboard typing, key presses, and hotkeys

The safety boundary is local and enforced before actions run:

- filesystem reads remain restricted by Sovereign's existing sandbox / selected-root / full-access policy
- filesystem writes are hidden unless `filesystem_write_enabled=true`
- writes still require explicit per-run approval
- desktop tools are hidden unless `computer_control_enabled=true`
- mouse and keyboard actions require explicit per-run approval
- screenshots are only exposed after computer control has been explicitly enabled
- PyAutoGUI's fail-safe remains enabled

## Core stack

- Python
- FastAPI
- Pydantic
- asyncio
- official OpenAI Python SDK
- MCP stdio tools
- pytest
- optional PyTorch local-ML extra

Desktop control adds optional PyAutoGUI, MSS, and Pillow dependencies.

## Install

Core:

    python -m pip install -e .

Development:

    python -m pip install -e ".[dev]"

Desktop control:

    python -m pip install -e ".[desktop]"

Optional local ML runtime:

    python -m pip install -e ".[ml]"

## Configuration

Example `~/.sovereign/config.json`:

    {
      "permission_mode": "sandbox",
      "workspace": "~/.sovereign/workspace",
      "filesystem_write_enabled": true,
      "computer_control_enabled": true,
      "backends": [
        {
          "name": "local-model",
          "endpoint": "http://127.0.0.1:11434/v1/chat/completions",
          "protocol": "openai",
          "model": "local-model",
          "capabilities": ["reasoning", "vision"],
          "priority": 100
        }
      ]
    }

Computer control remains disabled unless explicitly enabled.

## Run

List enabled tools:

    sovereign tools

Read-only tool use requires no special run flag because path policy still applies.

Approve a write for one run:

    sovereign run "Create notes.txt in my workspace" \
      --approve-tool sovereign__write_text

Approve mouse and keyboard actions for one run:

    sovereign run "Open the app and type hello" \
      --approve-tool sovereign__mouse_move \
      --approve-tool sovereign__mouse_click \
      --approve-tool sovereign__type_text

Approvals are exact tool names and apply only to that run.

## FastAPI

    sovereign serve --port 8765

Endpoints:

- `GET /health`
- `GET /v1/status`
- `GET /v1/tools`
- `POST /v1/route`
- `POST /v1/run`
- interactive OpenAPI docs at `/docs`

`POST /v1/run` accepts an `approved_tools` array for gated native actions.

## Permission model

- `sandbox`: Sovereign workspace only
- `selected`: workspace plus explicitly selected roots
- `full`: unrestricted path checks only when `full_access_opt_in=true`

Remote model output is never permission to bypass local policy or approval gates.

Current version: 6.9.0.
