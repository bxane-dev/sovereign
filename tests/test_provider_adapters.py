import asyncio

from sovereign.backend import BackendExecutor
from sovereign.models import BackendSpec, Capability


def test_ollama_adapter_preserves_images_and_tool_calls(monkeypatch):
    seen = {}

    def post(spec, payload, headers):
        seen.update(payload)
        return {"message": {"content": "", "tool_calls": [
            {"function": {"name": "sovereign__mouse_click", "arguments": {"x": 4, "y": 5}}}
        ]}}

    monkeypatch.setattr(BackendExecutor, "_post_json", staticmethod(post))
    spec = BackendSpec("ollama", "http://localhost:11434/api/chat", frozenset({Capability.VISION}), protocol="ollama", model="vision")
    messages = [{"role": "user", "content": [
        {"type": "text", "text": "inspect"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,aGVsbG8="}},
    ]}]
    reply = asyncio.run(BackendExecutor().complete(spec, messages, [], Capability.VISION))
    assert seen["stream"] is False
    assert seen["messages"][0] == {"role": "user", "content": "inspect", "images": ["aGVsbG8="]}
    assert reply.tool_calls[0].arguments == {"x": 4, "y": 5}


def test_anthropic_adapter_converts_system_image_and_tool_roundtrip(monkeypatch):
    seen = {}

    def post(spec, payload, headers):
        seen.update({"payload": payload, "headers": headers})
        return {"content": [
            {"type": "text", "text": "done"},
            {"type": "tool_use", "id": "toolu_2", "name": "echo", "input": {"text": "ok"}},
        ]}

    monkeypatch.setattr(BackendExecutor, "_post_json", staticmethod(post))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    spec = BackendSpec("claude", "https://api.anthropic.com/v1/messages", frozenset({Capability.VISION}), protocol="anthropic", model="example")
    messages = [
        {"role": "system", "content": "be careful"},
        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,aGVsbG8="}}]},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "toolu_1", "function": {"name": "echo", "arguments": '{"text":"hi"}'}}]},
        {"role": "tool", "tool_call_id": "toolu_1", "name": "echo", "content": '{"ok":true}'},
    ]
    tools = [{"function": {"name": "echo", "description": "Echo", "parameters": {"type": "object"}}}]
    reply = asyncio.run(BackendExecutor().complete(spec, messages, tools, Capability.VISION))
    payload = seen["payload"]
    assert payload["system"] == "be careful"
    assert payload["messages"][0]["content"][0]["source"] == {
        "type": "base64", "media_type": "image/png", "data": "aGVsbG8="
    }
    assert payload["messages"][1]["content"][0]["type"] == "tool_use"
    assert payload["messages"][2]["content"][0]["type"] == "tool_result"
    assert payload["tools"][0]["input_schema"] == {"type": "object"}
    assert seen["headers"]["x-api-key"] == "secret"
    assert reply.text == "done"
    assert reply.tool_calls[0].id == "toolu_2"
