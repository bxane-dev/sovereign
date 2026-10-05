from __future__ import annotations

import os
import secrets
import json
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import __version__
from .agent import SovereignAgent
from .config import DEFAULT_CONFIG
from .models import Capability


class AttachmentInfo(BaseModel):
    path: str
    media_type: str
    size: int
    sha256: str


class RouteRequest(BaseModel):
    capability: Capability
    attachments: list[str] = Field(default_factory=list)


class RouteResponse(BaseModel):
    capability: Capability
    backend: str
    attachments: list[AttachmentInfo] = Field(default_factory=list)


class RunRequest(BaseModel):
    prompt: str = Field(min_length=1)
    capability: Capability = Capability.REASONING
    attachments: list[str] = Field(default_factory=list)
    max_steps: int | None = Field(default=None, ge=1)
    approved_tools: list[str] = Field(default_factory=list)
    session_id: str | None = None


class RunResponse(BaseModel):
    text: str
    backend: str
    capability: Capability
    steps: int
    tool_calls: int


class ComputerRunRequest(BaseModel):
    prompt: str = Field(min_length=1)
    max_steps: int | None = Field(default=None, ge=1)
    approved_tools: list[str] = Field(default_factory=list)


class ComputerRunResponse(BaseModel):
    text: str
    backend: str
    frames: int
    tool_calls: int


class SessionCreateRequest(BaseModel):
    capability: Capability = Capability.REASONING


class SessionResumeRequest(BaseModel):
    max_steps: int | None = Field(default=None, ge=1)
    approved_tools: list[str] = Field(default_factory=list)


class ComputerControlSettingsRequest(BaseModel):
    enabled: bool


def create_app(agent: SovereignAgent) -> FastAPI:
    app = FastAPI(
        title="Sovereign",
        version=__version__,
        description="Local-first AI agent control plane.",
    )

    @app.middleware("http")
    async def require_local_token(request: Request, call_next):
        token = os.getenv("SOVEREIGN_API_TOKEN")
        if token and not secrets.compare_digest(
            request.headers.get("authorization", ""), f"Bearer {token}"
        ):
            return Response(status_code=401, content="Unauthorized")
        return await call_next(request)

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {"ok": True, "service": "sovereign", "version": __version__}

    @app.get("/v1/status")
    async def status() -> dict[str, object]:
        return agent.status()

    @app.get("/v1/tools")
    async def tools() -> dict[str, object]:
        return {
            "native_tools": agent.native_tools.names(),
            "visual_action_tools": agent.native_tools.visual_action_names(),
            "mcp_servers": agent.mcp.names(),
        }

    @app.post("/v1/settings/computer-control")
    async def computer_control_settings(request: ComputerControlSettingsRequest) -> dict[str, object]:
        config_path = DEFAULT_CONFIG.expanduser()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        settings: dict[str, object] = {}
        if config_path.exists():
            try:
                with config_path.open("r", encoding="utf-8") as handle:
                    loaded = json.load(handle)
            except (OSError, json.JSONDecodeError) as exc:
                raise HTTPException(status_code=400, detail=f"Could not read config file: {exc}") from exc
            if not isinstance(loaded, dict):
                raise HTTPException(status_code=400, detail="Config file must contain a JSON object")
            settings = loaded
        settings["computer_control_enabled"] = request.enabled
        settings["visual_autonomy_enabled"] = request.enabled
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=config_path.parent, delete=False) as handle:
                json.dump(settings, handle, indent=2)
                handle.write("\n")
                temp_name = handle.name
            os.replace(temp_name, config_path)
        except OSError as exc:
            if temp_name:
                try:
                    Path(temp_name).unlink(missing_ok=True)
                except OSError:
                    pass
            raise HTTPException(status_code=500, detail=f"Could not save computer-control settings: {exc}") from exc
        agent.config.computer_control_enabled = request.enabled
        agent.config.visual_autonomy_enabled = request.enabled
        return agent.status()

    @app.post("/v1/route", response_model=RouteResponse)
    async def route(request: RouteRequest) -> RouteResponse:
        try:
            decision = agent.plan_route(request.capability, request.attachments)
            return RouteResponse(
                capability=decision.capability,
                backend=decision.backend.name,
                attachments=[
                    AttachmentInfo(
                        path=str(item.path),
                        media_type=item.media_type,
                        size=item.size,
                        sha256=item.sha256,
                    )
                    for item in decision.attachments
                ],
            )
        except (ValueError, RuntimeError, PermissionError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/v1/run", response_model=RunResponse)
    async def run(request: RunRequest) -> RunResponse:
        try:
            result = await agent.run(
                request.prompt,
                request.capability,
                request.attachments,
                request.max_steps,
                request.approved_tools,
                request.session_id,
            )
            return RunResponse(
                text=result.text,
                backend=result.backend,
                capability=result.capability,
                steps=result.steps,
                tool_calls=result.tool_calls,
            )
        except (ValueError, RuntimeError, PermissionError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/v1/computer/run", response_model=ComputerRunResponse)
    async def computer_run(request: ComputerRunRequest) -> ComputerRunResponse:
        try:
            result = await agent.run_visual(
                request.prompt,
                request.approved_tools,
                request.max_steps,
            )
            return ComputerRunResponse(
                text=result.text,
                backend=result.backend,
                frames=result.frames,
                tool_calls=result.tool_calls,
            )
        except (ValueError, RuntimeError, PermissionError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/v1/sessions", status_code=201)
    async def create_session(request: SessionCreateRequest) -> dict[str, object]:
        return agent.sessions.create(request.capability).summary()

    @app.get("/v1/sessions")
    async def list_sessions() -> dict[str, object]:
        return {"sessions": [item.summary() for item in agent.sessions.list()]}

    @app.get("/v1/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, object]:
        try:
            session = agent.sessions.get(session_id)
            return {**session.summary(), "messages": session.messages}
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/v1/sessions/{session_id}/resume", response_model=RunResponse)
    async def resume_session(session_id: str, request: SessionResumeRequest) -> RunResponse:
        try:
            result = await agent.run(
                "", max_steps=request.max_steps, approved_tools=request.approved_tools,
                session_id=session_id, resume=True,
            )
            return RunResponse(
                text=result.text, backend=result.backend, capability=result.capability,
                steps=result.steps, tool_calls=result.tool_calls,
            )
        except (ValueError, RuntimeError, PermissionError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/v1/sessions/{session_id}", status_code=204)
    async def delete_session(session_id: str) -> Response:
        try:
            agent.sessions.delete(session_id)
            return Response(status_code=204)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app


def serve(agent: SovereignAgent, host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    if host not in {"127.0.0.1", "::1", "localhost"} and not os.getenv("SOVEREIGN_API_TOKEN"):
        raise ValueError("non-loopback API binding requires SOVEREIGN_API_TOKEN")
    uvicorn.run(create_app(agent), host=host, port=port, log_level="info")
