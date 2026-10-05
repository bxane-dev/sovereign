import asyncio
from pathlib import Path

import pytest

from sovereign.config import SovereignConfig
from sovereign.native_tools import ApprovalRequired, NativeToolRuntime
from sovereign.permissions import PermissionPolicy


class FakeDesktop:
    def __init__(self):
        self.actions = []

    def screen_size(self):
        return (1280, 720)

    def screenshot(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-png")
        self.actions.append(("screenshot", str(path)))
        return (1280, 720)

    def move_to(self, x, y, duration):
        self.actions.append(("move", x, y, duration))

    def click(self, x, y, button, clicks):
        self.actions.append(("click", x, y, button, clicks))

    def type_text(self, text, interval):
        self.actions.append(("type", text, interval))

    def press_key(self, key):
        self.actions.append(("key", key))

    def hotkey(self, keys):
        self.actions.append(("hotkey", list(keys)))


def make_runtime(tmp_path: Path, **overrides):
    cfg = SovereignConfig(
        workspace=tmp_path,
        filesystem_write_enabled=overrides.get("filesystem_write_enabled", False),
        computer_control_enabled=overrides.get("computer_control_enabled", False),
    )
    desktop = FakeDesktop()
    return cfg, desktop, NativeToolRuntime(cfg, PermissionPolicy(cfg), desktop)


def test_filesystem_read_and_write_approval(tmp_path: Path):
    cfg, _, runtime = make_runtime(tmp_path, filesystem_write_enabled=True)
    source = tmp_path / "source.txt"
    source.write_text("hello sovereign", encoding="utf-8")

    read = asyncio.run(runtime.execute(runtime.READ_TEXT, {"path": str(source)}))
    assert read["text"] == "hello sovereign"

    target = tmp_path / "created.txt"
    with pytest.raises(ApprovalRequired):
        asyncio.run(
            runtime.execute(
                runtime.WRITE_TEXT,
                {"path": str(target), "content": "created"},
            )
        )

    written = asyncio.run(
        runtime.execute(
            runtime.WRITE_TEXT,
            {"path": str(target), "content": "created"},
            [runtime.WRITE_TEXT],
        )
    )
    assert target.read_text(encoding="utf-8") == "created"
    assert written["chars"] == 7
    assert runtime.WRITE_TEXT in runtime.names()
    assert cfg.filesystem_write_enabled is True


def test_directory_listing_is_confined_to_policy(tmp_path: Path):
    _, _, runtime = make_runtime(tmp_path)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "folder").mkdir()

    result = asyncio.run(runtime.execute(runtime.LIST_DIRECTORY, {"path": str(tmp_path)}))
    assert [entry["name"] for entry in result["entries"]] == ["a.txt", "folder"]


def test_computer_tools_are_hidden_until_enabled(tmp_path: Path):
    _, _, runtime = make_runtime(tmp_path)
    names = runtime.names()
    assert runtime.SCREENSHOT not in names
    assert runtime.MOUSE_CLICK not in names


def test_desktop_read_and_input_approval(tmp_path: Path):
    _, desktop, runtime = make_runtime(tmp_path, computer_control_enabled=True)

    size = asyncio.run(runtime.execute(runtime.SCREEN_SIZE, {}))
    assert size == {"width": 1280, "height": 720}

    shot = asyncio.run(runtime.execute(runtime.SCREENSHOT, {}))
    assert Path(shot["path"]).is_file()
    assert shot["width"] == 1280

    with pytest.raises(ApprovalRequired):
        asyncio.run(runtime.execute(runtime.MOUSE_CLICK, {"x": 10, "y": 20}))

    click = asyncio.run(
        runtime.execute(
            runtime.MOUSE_CLICK,
            {"x": 10, "y": 20, "button": "left", "clicks": 1},
            [runtime.MOUSE_CLICK],
        )
    )
    assert click["x"] == 10
    assert desktop.actions[-1] == ("click", 10, 20, "left", 1)
