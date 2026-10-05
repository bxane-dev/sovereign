from pathlib import Path

import pytest

from sovereign.config import SovereignConfig
from sovereign.models import PermissionMode
from sovereign.permissions import PermissionDenied, PermissionPolicy


def test_sandbox_allows_workspace(tmp_path: Path):
    workspace = tmp_path / "workspace"
    policy = PermissionPolicy(SovereignConfig(workspace=workspace))
    assert policy.check_path(workspace / "file.txt") == (workspace / "file.txt").resolve()


def test_sandbox_denies_outside_workspace(tmp_path: Path):
    policy = PermissionPolicy(SovereignConfig(workspace=tmp_path / "workspace"))
    with pytest.raises(PermissionDenied):
        policy.check_path(tmp_path / "outside.txt")


def test_selected_allows_selected_root(tmp_path: Path):
    root = tmp_path / "selected"
    cfg = SovereignConfig(permission_mode=PermissionMode.SELECTED, workspace=tmp_path / "workspace", allowed_roots=[root])
    assert PermissionPolicy(cfg).check_path(root / "x") == (root / "x").resolve()


def test_full_requires_explicit_opt_in(tmp_path: Path):
    cfg = SovereignConfig(permission_mode=PermissionMode.FULL, full_access_opt_in=False)
    with pytest.raises(PermissionDenied):
        PermissionPolicy(cfg).check_path(tmp_path)


def test_full_allows_any_path_after_opt_in(tmp_path: Path):
    cfg = SovereignConfig(permission_mode=PermissionMode.FULL, full_access_opt_in=True)
    assert PermissionPolicy(cfg).check_path(tmp_path) == tmp_path.resolve()
