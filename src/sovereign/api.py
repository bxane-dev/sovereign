from __future__ import annotations

import asyncio
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .agent import SovereignAgent
from .models import Capability


class SovereignHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], agent: SovereignAgent):
        self.agent = agent
        super().__init__(server_address, SovereignRequestHandler)


class SovereignRequestHandler(BaseHTTPRequestHandler):
    server: SovereignHTTPServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _payload(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 1024 * 1024:
            raise ValueError("invalid request body size")
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(HTTPStatus.OK, {"ok": True, "service": "sovereign"})
            return
        if self.path == "/v1/status":
            self._json(HTTPStatus.OK, self.server.agent.status())
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:
        try:
            payload = self._payload()
            if self.path == "/v1/route":
                capability = Capability(str(payload["capability"]))
                attachments = payload.get("attachments", [])
                if not isinstance(attachments, list):
                    raise ValueError("attachments must be an array")
                decision = self.server.agent.plan_route(capability, attachments)
                self._json(
                    HTTPStatus.OK,
                    {
                        "capability": decision.capability.value,
                        "backend": decision.backend.name,
                        "attachments": [
                            {
                                "path": str(item.path),
                                "media_type": item.media_type,
                                "size": item.size,
                                "sha256": item.sha256,
                            }
                            for item in decision.attachments
                        ],
                    },
                )
                return
            if self.path == "/v1/run":
                prompt = str(payload["prompt"])
                capability = Capability(str(payload.get("capability", "reasoning")))
                attachments = payload.get("attachments", [])
                if not isinstance(attachments, list):
                    raise ValueError("attachments must be an array")
                raw_steps = payload.get("max_steps")
                result = asyncio.run(
                    self.server.agent.run(
                        prompt,
                        capability,
                        attachments,
                        int(raw_steps) if raw_steps is not None else None,
                    )
                )
                self._json(
                    HTTPStatus.OK,
                    {
                        "text": result.text,
                        "backend": result.backend,
                        "capability": result.capability.value,
                        "steps": result.steps,
                        "tool_calls": result.tool_calls,
                    },
                )
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
        except (KeyError, ValueError, RuntimeError, PermissionError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})


def serve(agent: SovereignAgent, host: str = "127.0.0.1", port: int = 8765) -> None:
    server = SovereignHTTPServer((host, port), agent)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
