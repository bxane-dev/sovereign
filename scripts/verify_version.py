"""Require matching v8 package versions before a release build."""

import json
import sys
import tomllib
from pathlib import Path


root = Path(__file__).resolve().parents[1]
versions = {
    "python": tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"],
    "desktop": json.loads((root / "apps/desktop/package.json").read_text())["version"],
    "terminal": json.loads((root / "apps/terminal/package.json").read_text())["version"],
}
expected = sys.argv[1].removeprefix("v") if len(sys.argv) > 1 else versions["python"]
if not all(version == expected for version in versions.values()):
    raise SystemExit(f"version mismatch: expected {expected}, found {versions}")
print(f"Version {expected} is consistent")
