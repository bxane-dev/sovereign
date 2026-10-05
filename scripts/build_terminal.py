"""Compile the Bun terminal into Electron's bundled resources."""

import subprocess
import sys
from pathlib import Path


root = Path(__file__).resolve().parents[1]
name = "sovereign-terminal.exe" if sys.platform == "win32" else "sovereign-terminal"
target = root / "apps" / "desktop" / "resources" / "terminal" / name
target.parent.mkdir(parents=True, exist_ok=True)
subprocess.run(
    ["pnpm", "--filter", "@sovereign/terminal", "exec", "bun", "build", "src/index.tsx", "--compile", "--outfile", str(target)],
    cwd=root,
    check=True,
)
