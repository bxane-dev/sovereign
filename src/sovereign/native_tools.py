from __future__ import annotations

import asyncio
import hashlib
import uuid
from pathlib import Path
from typing import Any, Iterable, Protocol

from .config import SovereignConfig
from .permissions import PermissionPolicy


class ApprovalRequired(PermissionError):
    pass


class NativeToolError(RuntimeError):
    pass


class DesktopDriver(Protocol):
    def screen_size(self) -> tuple[int, int]: ...
    def screenshot(self, path: Path) -> tuple[int, int]: ...
    def move_to(self, x: int, y: int, duration: float) -> None: ...
    def click(self, x: int, y: int, button: str, clicks: int) -> None: ...
    def type_text(self, text: str, interval: float) -> None: ...
    def press_key(self, key: str) -> None: ...
    def hotkey(self, keys: list[str]) -> None: ...


class PyAutoGUIDriver:
    def __init__(self) -> None:
        try:
            import mss
            import pyautogui
            from PIL import Image
        except ImportError as exc:
            raise NativeToolError(
                'desktop tools require: pip install -e ".[desktop]"'
            ) from exc
        pyautogui.FAILSAFE = True
        self._pyautogui = pyautogui
        self._mss = mss
        self._image = Image

    def screen_size(self) -> tuple[int, int]:
        size = self._pyautogui.size()
        return int(size.width), int(size.height)

    def screenshot(self, path: Path) -> tuple[int, int]:
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._mss.mss() as capture:
            monitor = capture.monitors[0]
            shot = capture.grab(monitor)
            image = self._image.frombytes("RGB", shot.size, shot.rgb)
            image.save(path, format="PNG")
            return int(shot.width), int(shot.height)

    def move_to(self, x: int, y: int, duration: float) -> None:
        self._pyautogui.moveTo(x, y, duration=duration)

    def click(self, x: int, y: int, button: str, clicks: int) -> None:
        self._pyautogui.click(x=x, y=y, button=button, clicks=clicks)

    def type_text(self, text: str, interval: float) -> None:
        self._pyautogui.write(text, interval=interval)

    def press_key(self, key: str) -> None:
        self._pyautogui.press(key)

    def hotkey(self, keys: list[str]) -> None:
        self._pyautogui.hotkey(*keys)


class NativeToolRuntime:
    READ_TEXT = "sovereign__read_text"
    LIST_DIRECTORY = "sovereign__list_directory"
    WRITE_TEXT = "sovereign__write_text"
    SCREEN_SIZE = "sovereign__screen_size"
    SCREENSHOT = "sovereign__screenshot"
    MOUSE_MOVE = "sovereign__mouse_move"
    MOUSE_CLICK = "sovereign__mouse_click"
    TYPE_TEXT = "sovereign__type_text"
    PRESS_KEY = "sovereign__press_key"
    HOTKEY = "sovereign__hotkey"

    _APPROVAL_REQUIRED = {
        WRITE_TEXT,
        MOUSE_MOVE,
        MOUSE_CLICK,
        TYPE_TEXT,
        PRESS_KEY,
        HOTKEY,
    }

    def __init__(
        self,
        config: SovereignConfig,
        policy: PermissionPolicy,
        desktop_driver: DesktopDriver | None = None,
    ):
        self.config = config
        self.policy = policy
        self._desktop_driver = desktop_driver

    def _desktop(self) -> DesktopDriver:
        if not self.config.computer_control_enabled:
            raise NativeToolError("computer control is disabled")
        if self._desktop_driver is None:
            self._desktop_driver = PyAutoGUIDriver()
        return self._desktop_driver

    def definitions(self) -> list[dict[str, Any]]:
        if not self.config.native_tools_enabled:
            return []

        definitions: list[dict[str, Any]] = [
            self._definition(
                self.READ_TEXT,
                "Read a UTF-8 text file inside Sovereign's permitted filesystem roots.",
                {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "max_chars": {"type": "integer", "minimum": 1},
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            ),
            self._definition(
                self.LIST_DIRECTORY,
                "List a directory inside Sovereign's permitted filesystem roots.",
                {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            ),
        ]

        if self.config.filesystem_write_enabled:
            definitions.append(
                self._definition(
                    self.WRITE_TEXT,
                    "Write UTF-8 text inside permitted roots. Requires explicit per-run approval.",
                    {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                            "overwrite": {"type": "boolean"},
                        },
                        "required": ["path", "content"],
                        "additionalProperties": False,
                    },
                )
            )

        if self.config.computer_control_enabled:
            definitions.extend(
                [
                    self._definition(
                        self.SCREEN_SIZE,
                        "Return the desktop screen size.",
                        {"type": "object", "properties": {}, "additionalProperties": False},
                    ),
                    self._definition(
                        self.SCREENSHOT,
                        "Capture the desktop to a PNG inside Sovereign's permitted roots.",
                        {
                            "type": "object",
                            "properties": {"path": {"type": "string"}},
                            "additionalProperties": False,
                        },
                    ),
                    self._definition(
                        self.MOUSE_MOVE,
                        "Move the mouse pointer. Requires explicit per-run approval.",
                        {
                            "type": "object",
                            "properties": {
                                "x": {"type": "integer", "minimum": 0},
                                "y": {"type": "integer", "minimum": 0},
                                "duration": {"type": "number", "minimum": 0, "maximum": 10},
                            },
                            "required": ["x", "y"],
                            "additionalProperties": False,
                        },
                    ),
                    self._definition(
                        self.MOUSE_CLICK,
                        "Click the mouse. Requires explicit per-run approval.",
                        {
                            "type": "object",
                            "properties": {
                                "x": {"type": "integer", "minimum": 0},
                                "y": {"type": "integer", "minimum": 0},
                                "button": {"type": "string", "enum": ["left", "middle", "right"]},
                                "clicks": {"type": "integer", "minimum": 1, "maximum": 5},
                            },
                            "required": ["x", "y"],
                            "additionalProperties": False,
                        },
                    ),
                    self._definition(
                        self.TYPE_TEXT,
                        "Type text with the keyboard. Requires explicit per-run approval.",
                        {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string", "maxLength": 10000},
                                "interval": {"type": "number", "minimum": 0, "maximum": 0.5},
                            },
                            "required": ["text"],
                            "additionalProperties": False,
                        },
                    ),
                    self._definition(
                        self.PRESS_KEY,
                        "Press one keyboard key. Requires explicit per-run approval.",
                        {
                            "type": "object",
                            "properties": {"key": {"type": "string", "minLength": 1, "maxLength": 32}},
                            "required": ["key"],
                            "additionalProperties": False,
                        },
                    ),
                    self._definition(
                        self.HOTKEY,
                        "Press a keyboard shortcut. Requires explicit per-run approval.",
                        {
                            "type": "object",
                            "properties": {
                                "keys": {
                                    "type": "array",
                                    "items": {"type": "string", "minLength": 1, "maxLength": 32},
                                    "minItems": 1,
                                    "maxItems": 5,
                                }
                            },
                            "required": ["keys"],
                            "additionalProperties": False,
                        },
                    ),
                ]
            )
        return definitions

    @staticmethod
    def _definition(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        }

    def names(self) -> list[str]:
        return [item["function"]["name"] for item in self.definitions()]

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        approved_tools: Iterable[str] = (),
    ) -> dict[str, Any]:
        available = set(self.names())
        if name not in available:
            raise NativeToolError(f"native tool is disabled or unknown: {name}")
        approvals = set(approved_tools)
        if name in self._APPROVAL_REQUIRED and name not in approvals:
            raise ApprovalRequired(
                f"{name} requires explicit approval; rerun with approval for this tool"
            )
        handler = {
            self.READ_TEXT: self._read_text,
            self.LIST_DIRECTORY: self._list_directory,
            self.WRITE_TEXT: self._write_text,
            self.SCREEN_SIZE: self._screen_size,
            self.SCREENSHOT: self._screenshot,
            self.MOUSE_MOVE: self._mouse_move,
            self.MOUSE_CLICK: self._mouse_click,
            self.TYPE_TEXT: self._type_text,
            self.PRESS_KEY: self._press_key,
            self.HOTKEY: self._hotkey,
        }[name]
        return await asyncio.to_thread(handler, arguments)

    def _read_text(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = self.policy.check_path(str(arguments["path"]))
        if not path.is_file():
            raise NativeToolError(f"not a file: {path}")
        requested = int(arguments.get("max_chars", self.config.max_native_read_chars))
        limit = min(max(requested, 1), self.config.max_native_read_chars)
        text = path.read_text(encoding="utf-8", errors="replace")
        truncated = len(text) > limit
        return {
            "path": str(path),
            "text": text[:limit],
            "truncated": truncated,
            "chars": min(len(text), limit),
        }

    def _list_directory(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = self.policy.check_path(str(arguments["path"]))
        if not path.is_dir():
            raise NativeToolError(f"not a directory: {path}")
        limit = min(max(int(arguments.get("limit", 200)), 1), 500)
        entries = []
        for child in sorted(path.iterdir(), key=lambda item: item.name.lower())[:limit]:
            checked = self.policy.check_path(child)
            entries.append(
                {
                    "name": checked.name,
                    "path": str(checked),
                    "type": "directory" if checked.is_dir() else "file" if checked.is_file() else "other",
                    "size": checked.stat().st_size if checked.is_file() else None,
                }
            )
        return {"path": str(path), "entries": entries, "count": len(entries)}

    def _write_text(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = self.policy.check_path(str(arguments["path"]))
        content = str(arguments["content"])
        if len(content) > self.config.max_native_write_chars:
            raise NativeToolError(
                f"write exceeds {self.config.max_native_write_chars} characters"
            )
        overwrite = bool(arguments.get("overwrite", False))
        if path.exists() and not overwrite:
            raise NativeToolError("target already exists; set overwrite=true to replace it")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {
            "path": str(path),
            "chars": len(content),
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        }

    def _screen_size(self, arguments: dict[str, Any]) -> dict[str, Any]:
        width, height = self._desktop().screen_size()
        return {"width": width, "height": height}

    def _screenshot(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw_path = arguments.get("path")
        if raw_path:
            path = self.policy.check_path(str(raw_path))
        else:
            path = self.policy.check_path(
                self.config.workspace / "screenshots" / f"screenshot-{uuid.uuid4().hex}.png"
            )
        width, height = self._desktop().screenshot(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return {
            "path": str(path),
            "width": width,
            "height": height,
            "sha256": digest,
        }

    def _validate_point(self, x: int, y: int) -> tuple[int, int]:
        width, height = self._desktop().screen_size()
        if x < 0 or y < 0 or x >= width or y >= height:
            raise NativeToolError(f"coordinates ({x}, {y}) are outside {width}x{height}")
        return x, y

    def _mouse_move(self, arguments: dict[str, Any]) -> dict[str, Any]:
        x, y = self._validate_point(int(arguments["x"]), int(arguments["y"]))
        duration = min(max(float(arguments.get("duration", 0.0)), 0.0), 10.0)
        self._desktop().move_to(x, y, duration)
        return {"x": x, "y": y, "duration": duration}

    def _mouse_click(self, arguments: dict[str, Any]) -> dict[str, Any]:
        x, y = self._validate_point(int(arguments["x"]), int(arguments["y"]))
        button = str(arguments.get("button", "left"))
        if button not in {"left", "middle", "right"}:
            raise NativeToolError(f"unsupported mouse button: {button}")
        clicks = min(max(int(arguments.get("clicks", 1)), 1), 5)
        self._desktop().click(x, y, button, clicks)
        return {"x": x, "y": y, "button": button, "clicks": clicks}

    def _type_text(self, arguments: dict[str, Any]) -> dict[str, Any]:
        text = str(arguments["text"])
        if len(text) > 10_000:
            raise NativeToolError("text is limited to 10000 characters")
        interval = min(max(float(arguments.get("interval", 0.0)), 0.0), 0.5)
        self._desktop().type_text(text, interval)
        return {"typed_chars": len(text), "interval": interval}

    def _press_key(self, arguments: dict[str, Any]) -> dict[str, Any]:
        key = str(arguments["key"]).strip()
        if not key or len(key) > 32:
            raise NativeToolError("invalid key")
        self._desktop().press_key(key)
        return {"key": key}

    def _hotkey(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw_keys = arguments["keys"]
        if not isinstance(raw_keys, list) or not 1 <= len(raw_keys) <= 5:
            raise NativeToolError("hotkey requires 1 to 5 keys")
        keys = [str(key).strip() for key in raw_keys]
        if any(not key or len(key) > 32 for key in keys):
            raise NativeToolError("invalid hotkey")
        self._desktop().hotkey(keys)
        return {"keys": keys}
