from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Any

from .mesh import ComputeMesh
from .models import BackendReply, BackendSpec, Capability, ToolCall


class BackendExecutionError(RuntimeError):
    pass


class BackendExecutor:
    """Executes a normalized Sovereign conversation against a configured backend."""

    async def complete(
        self,
        spec: BackendSpec,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        capability: Capability,
    ) -> BackendReply:
        return await asyncio.to_thread(self._complete_sync, spec, messages, tools, capability)

    def _complete_sync(
        self,
        spec: BackendSpec,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        capability: Capability,
    ) -> BackendReply:
        if spec.protocol == "openai":
            payload = dict(spec.options)
            payload.update({"model": spec.model or "default", "messages": messages})
            if tools:
                payload["tools"] = tools
                payload.setdefault("tool_choice", "auto")
        elif spec.protocol == "sovereign":
            payload = dict(spec.options)
            payload.update(
                {
                    "capability": capability.value,
                    "model": spec.model,
                    "messages": messages,
                    "tools": tools,
                }
            )
        else:
            raise BackendExecutionError(f"unsupported backend protocol: {spec.protocol}")

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        headers.update(ComputeMesh.resolved_headers(spec))
        request = urllib.request.Request(
            spec.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=spec.timeout_seconds) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:1000]
            raise BackendExecutionError(f"backend {spec.name!r} returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BackendExecutionError(f"backend {spec.name!r} request failed: {exc}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BackendExecutionError(f"backend {spec.name!r} returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise BackendExecutionError(f"backend {spec.name!r} returned a non-object JSON response")
        return self._parse_openai(data) if spec.protocol == "openai" else self._parse_sovereign(data)

    @staticmethod
    def _parse_openai(data: dict[str, Any]) -> BackendReply:
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise BackendExecutionError("OpenAI-compatible response is missing choices[0].message") from exc
        content = message.get("content")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = "".join(
                str(block.get("text", ""))
                for block in content
                if isinstance(block, dict) and block.get("type") in {"text", "output_text"}
            )
        else:
            text = ""
        calls: list[ToolCall] = []
        for index, item in enumerate(message.get("tool_calls") or []):
            if not isinstance(item, dict):
                continue
            function = item.get("function") or {}
            if not isinstance(function, dict) or not function.get("name"):
                continue
            raw_args = function.get("arguments", {})
            if isinstance(raw_args, str):
                try:
                    arguments = json.loads(raw_args) if raw_args else {}
                except json.JSONDecodeError as exc:
                    raise BackendExecutionError(f"tool call {function.get('name')!r} has invalid JSON arguments") from exc
            elif isinstance(raw_args, dict):
                arguments = raw_args
            else:
                raise BackendExecutionError(f"tool call {function.get('name')!r} arguments must be an object")
            if not isinstance(arguments, dict):
                raise BackendExecutionError(f"tool call {function.get('name')!r} arguments must decode to an object")
            calls.append(
                ToolCall(
                    id=str(item.get("id") or f"call_{index + 1}"),
                    name=str(function["name"]),
                    arguments=arguments,
                )
            )
        return BackendReply(text=text, tool_calls=tuple(calls))

    @staticmethod
    def _parse_sovereign(data: dict[str, Any]) -> BackendReply:
        text = str(data.get("text", ""))
        calls: list[ToolCall] = []
        for index, item in enumerate(data.get("tool_calls") or []):
            if not isinstance(item, dict) or not item.get("name"):
                continue
            arguments = item.get("arguments", {})
            if not isinstance(arguments, dict):
                raise BackendExecutionError(f"tool call {item.get('name')!r} arguments must be an object")
            calls.append(
                ToolCall(
                    id=str(item.get("id") or f"call_{index + 1}"),
                    name=str(item["name"]),
                    arguments=arguments,
                )
            )
        return BackendReply(text=text, tool_calls=tuple(calls))
