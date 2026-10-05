from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import __version__
from .agent import SovereignAgent
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


class RunResponse(BaseModel):
    text: str
    backend: str
    capability: Capability
    steps: int
    tool_calls: int


def create_app(agent: SovereignAgent) -> FastAPI:
    app = FastAPI(
        title="Sovereign",
        version=__version__,
        description="Local-first AI agent control plane.",
    )

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {"ok": True, "service": "sovereign", "version": __version__}

    @app.get("/v1/status")
    async def status() -> dict[str, object]:
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

    return app


def serve(agent: SovereignAgent, host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    uvicorn.run(create_app(agent), host=host, port=port, log_level="info")
