from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path

from .models import Attachment
from .permissions import PermissionPolicy


class AttachmentError(ValueError):
    pass


class AttachmentInspector:
    def __init__(self, policy: PermissionPolicy, max_bytes: int):
        self.policy = policy
        self.max_bytes = max_bytes

    def inspect(self, path: Path | str) -> Attachment:
        target = self.policy.check_path(path)
        if not target.is_file():
            raise AttachmentError(f"not a file: {target}")
        size = target.stat().st_size
        if size > self.max_bytes:
            raise AttachmentError(f"attachment exceeds {self.max_bytes} bytes")
        digest = hashlib.sha256()
        with target.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return Attachment(path=target, media_type=media_type, size=size, sha256=digest.hexdigest())
