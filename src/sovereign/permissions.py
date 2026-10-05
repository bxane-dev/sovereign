from __future__ import annotations

from pathlib import Path

from .config import SovereignConfig
from .models import PermissionMode


class PermissionDenied(PermissionError):
    pass


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class PermissionPolicy:
    def __init__(self, config: SovereignConfig):
        self.config = config

    def allowed_roots(self) -> tuple[Path, ...]:
        workspace = _resolved(self.config.workspace)
        if self.config.permission_mode is PermissionMode.SANDBOX:
            return (workspace,)
        if self.config.permission_mode is PermissionMode.SELECTED:
            roots = [workspace, *(_resolved(p) for p in self.config.allowed_roots)]
            return tuple(dict.fromkeys(roots))
        if self.config.permission_mode is PermissionMode.FULL:
            if not self.config.full_access_opt_in:
                raise PermissionDenied("full access requires full_access_opt_in=true")
            return tuple()
        raise PermissionDenied("unknown permission mode")

    def check_path(self, path: Path | str) -> Path:
        candidate = _resolved(Path(path))
        if self.config.permission_mode is PermissionMode.FULL:
            if not self.config.full_access_opt_in:
                raise PermissionDenied("full access requires explicit opt-in")
            return candidate
        if any(_within(candidate, root) for root in self.allowed_roots()):
            return candidate
        raise PermissionDenied(f"path is outside Sovereign's allowed roots: {candidate}")
