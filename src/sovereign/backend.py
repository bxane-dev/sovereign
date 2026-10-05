from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from typing import Any

from .mesh import ComputeMesh
from .models import BackendReply, BackendSpec, Capability, ToolCall


class BackendExecutionError(RuntimeError):
    pass


class BackendExecutor:
    """Executes normalized Sovereign conversations against configured backends."""

    async def complete(
        self,
        spec: BackendSpec,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        capability: Capability,
    ) -> BackendReply:
        if spec.protocol == "openai":
            return await self._complete_openai(spec, messages, tools)
        if spec.protocol == "sovereign":
            return await asyncio.to_thread(self._complete_sovereign_sync, spec, messages, tools, capability)
        raise BackendExecutionError(f"unsupported backend protocol: {spec.protocol}")

    @staticmethod
    def _openai_base_url(endpoint: str) -> str:
        normalized = endpoint.rstrip("/")
        suffix = "/chat/completions"
        return normalized[: -len(suffix)] if normalized.endswith(suffix) else normalized

    async def _complete_openai(
        self,
        spec: BackendSpec,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> BackendReply:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise BackendExecutionError("OpenAI SDK is not installed") from exc

        headers = ComputeMesh.resolved_headers(spec)
        raw_auth = headers.pop("Authorization", None)
        if raw_auth and raw_auth.lower().startswith("bearer "):
            api_key = raw_auth[7:].strip()
        else:
            api_key = os.getenv("OPENAI_API_KEY") or "sovereign-local"
            if raw_auth:
                headers["Authorization"] = raw_auth

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=self._openai_base_url(spec.endpoint),
            timeout=spec.timeout_seconds,
            max_retries=0,
            default_headers=headers or None,
        )
        params: dict[str, Any] = {
            "model": spec.model or "default",
            "messages": messages,
        }
        params.update(dict(spec.options))
        if tools:
            params["tools"] = tools
            params.setdefault("tool_choice", "auto")
        try:
            response = await client.chat.completions.create(**params)
        except Exception as exc:
            raise BackendExecutionError(f"backend {spec.name!r} request failed: {exc}") from exc
        finally:
            await client.close()

        data = response.model_dump(mode="json")
        if not isinstance(data, dict):
            raise BackendExecutionError(f"backend {spec.name!r} returned an invalid SDK response")
        return self._parse_openai(data)

    def _complete_sovereign_sync(
        self,
        spec: BackendSpec,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        capability: Capability,
    ) -> BackendReply:
        payload = dict(spec.options)
        payload.update(
            {
                "capability": capability.value,
                "model": spec.model,
                "messages": messages,
                "tools": tools,
            }
        )
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
        return self._parse_sovereign(data)

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
