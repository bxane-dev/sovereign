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
        if spec.protocol == "ollama":
            return await asyncio.to_thread(self._complete_ollama_sync, spec, messages, tools)
        if spec.protocol == "anthropic":
            return await asyncio.to_thread(self._complete_anthropic_sync, spec, messages, tools)
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
    def _post_json(spec: BackendSpec, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
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
            raise BackendExecutionError(f"backend {spec.name!r} returned a non-object response")
        return data

    @staticmethod
    def _ollama_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted = []
        for message in messages:
            role = message["role"]
            content = message.get("content")
            images: list[str] = []
            if isinstance(content, list):
                parts = []
                for block in content:
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    elif block.get("type") == "image_url":
                        url = block["image_url"]["url"]
                        if not url.startswith("data:image/") or ";base64," not in url:
                            raise BackendExecutionError("Ollama requires inline base64 images")
                        images.append(url.split(",", 1)[1])
                content = "\n".join(parts)
            item: dict[str, Any] = {"role": role, "content": content or ""}
            if images:
                item["images"] = images
            if role == "assistant" and message.get("tool_calls"):
                item["tool_calls"] = [
                    {
                        "function": {
                            "name": call["function"]["name"],
                            "arguments": json.loads(call["function"]["arguments"]),
                        }
                    }
                    for call in message["tool_calls"]
                ]
            converted.append(item)
        return converted

    def _complete_ollama_sync(
        self, spec: BackendSpec, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> BackendReply:
        if not spec.model:
            raise BackendExecutionError("Ollama backend requires a model")
        payload = {
            **dict(spec.options),
            "model": spec.model,
            "messages": self._ollama_messages(messages),
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        headers = {"Content-Type": "application/json", **ComputeMesh.resolved_headers(spec)}
        data = self._post_json(spec, payload, headers)
        message = data.get("message")
        if not isinstance(message, dict):
            raise BackendExecutionError("Ollama response is missing message")
        calls = []
        for index, item in enumerate(message.get("tool_calls") or []):
            function = item.get("function", {})
            arguments = function.get("arguments", {})
            if not function.get("name") or not isinstance(arguments, dict):
                raise BackendExecutionError("Ollama returned an invalid tool call")
            calls.append(ToolCall(
                id=str(item.get("id") or f"call_{index + 1}"),
                name=str(function["name"]), arguments=arguments,
            ))
        return BackendReply(text=str(message.get("content") or ""), tool_calls=tuple(calls))

    @staticmethod
    def _anthropic_messages(
        messages: list[dict[str, Any]],
    ) -> tuple[str | None, list[dict[str, Any]]]:
        system_parts: list[str] = []
        converted: list[dict[str, Any]] = []
        for message in messages:
            role = message["role"]
            content = message.get("content")
            if role == "system":
                system_parts.append(str(content or ""))
                continue
            if role == "tool":
                block = {
                    "type": "tool_result",
                    "tool_use_id": message["tool_call_id"],
                    "content": str(content or ""),
                }
                if converted and converted[-1]["role"] == "user" and isinstance(converted[-1]["content"], list) and converted[-1]["content"][0].get("type") == "tool_result":
                    converted[-1]["content"].append(block)
                else:
                    converted.append({"role": "user", "content": [block]})
                continue
            blocks: list[dict[str, Any]] = []
            if isinstance(content, str) and content:
                blocks.append({"type": "text", "text": content})
            elif isinstance(content, list):
                for block in content:
                    if block.get("type") == "text":
                        blocks.append({"type": "text", "text": block.get("text", "")})
                    elif block.get("type") == "image_url":
                        url = block["image_url"]["url"]
                        if not url.startswith("data:image/") or ";base64," not in url:
                            raise BackendExecutionError("Anthropic requires inline base64 images")
                        media_type = url[5:].split(";", 1)[0]
                        blocks.append({
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": url.split(",", 1)[1]},
                        })
            if role == "assistant":
                for call in message.get("tool_calls") or []:
                    blocks.append({
                        "type": "tool_use", "id": call["id"],
                        "name": call["function"]["name"],
                        "input": json.loads(call["function"]["arguments"]),
                    })
            converted.append({"role": role, "content": blocks})
        return "\n".join(system_parts) or None, converted

    def _complete_anthropic_sync(
        self, spec: BackendSpec, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> BackendReply:
        if not spec.model:
            raise BackendExecutionError("Anthropic backend requires a model")
        system, converted = self._anthropic_messages(messages)
        payload: dict[str, Any] = {
            **dict(spec.options), "model": spec.model,
            "max_tokens": spec.options.get("max_tokens", 1024),
            "messages": converted,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [
                {
                    "name": item["function"]["name"],
                    "description": item["function"].get("description", ""),
                    "input_schema": item["function"]["parameters"],
                }
                for item in tools
            ]
        headers = ComputeMesh.resolved_headers(spec)
        api_key = headers.pop("x-api-key", None) or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise BackendExecutionError("Anthropic backend requires ANTHROPIC_API_KEY")
        data = self._post_json(spec, payload, {
            "Content-Type": "application/json", "x-api-key": api_key,
            "anthropic-version": "2023-06-01", **headers,
        })
        blocks = data.get("content")
        if not isinstance(blocks, list):
            raise BackendExecutionError("Anthropic response is missing content")
        text = "".join(str(block.get("text", "")) for block in blocks if block.get("type") == "text")
        calls = []
        for block in blocks:
            if block.get("type") == "tool_use":
                if not block.get("id") or not block.get("name") or not isinstance(block.get("input"), dict):
                    raise BackendExecutionError("Anthropic returned an invalid tool call")
                calls.append(ToolCall(
                    id=str(block["id"]), name=str(block["name"]), arguments=block["input"]
                ))
        return BackendReply(text=text, tool_calls=tuple(calls))

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
