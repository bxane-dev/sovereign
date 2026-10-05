"""Build the Python sidecar in the location expected by electron-builder."""

from pathlib import Path

import PyInstaller.__main__


root = Path(__file__).resolve().parents[1]
PyInstaller.__main__.run(
    [
        str(root / "scripts" / "sovereign_core.py"),
        "--onefile",
        "--clean",
        "--noconfirm",
        "--name=sovereign-core",
        f"--distpath={root / 'apps' / 'desktop' / 'resources' / 'core'}",
        f"--workpath={root / 'work' / 'pyinstaller'}",
        f"--specpath={root / 'work' / 'pyinstaller'}",
        "--collect-submodules=sovereign",
    ]
)
