"""Durable, single-process agent conversation checkpoints."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Capability


class SessionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SessionRecord:
    id: str
    capability: Capability
    status: str
    messages: list[dict[str, Any]]
    created_at: str
    updated_at: str
    error: str | None

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "capability": self.capability.value,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
            "message_count": len(self.messages),
        }


class SessionStore:
    def __init__(self, path: Path):
        self.path = path
        self._initialized = False

    @contextmanager
    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        if not self._initialized:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    capability TEXT NOT NULL,
                    status TEXT NOT NULL,
                    messages TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error TEXT
                )"""
            )
            # A process restart cannot know whether its last action took effect.
            connection.execute(
                "UPDATE sessions SET status = 'interrupted', error = 'process stopped during run' "
                "WHERE status = 'running'"
            )
            connection.commit()
            self._initialized = True
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _record(row: sqlite3.Row) -> SessionRecord:
        return SessionRecord(
            id=row["id"],
            capability=Capability(row["capability"]),
            status=row["status"],
            messages=json.loads(row["messages"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            error=row["error"],
        )

    def create(self, capability: Capability = Capability.REASONING) -> SessionRecord:
        now = datetime.now(timezone.utc).isoformat()
        identifier = uuid.uuid4().hex
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?)",
                (identifier, capability.value, "idle", "[]", now, now, None),
            )
        return self.get(identifier)

    def get(self, identifier: str) -> SessionRecord:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM sessions WHERE id = ?", (identifier,)).fetchone()
        if row is None:
            raise SessionError(f"unknown session: {identifier}")
        return self._record(row)

    def list(self, limit: int = 50) -> list[SessionRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?",
                (min(max(limit, 1), 200),),
            ).fetchall()
        return [self._record(row) for row in rows]

    def checkpoint(
        self,
        identifier: str,
        messages: list[dict[str, Any]],
        status: str,
        error: str | None = None,
    ) -> None:
        if status not in {"idle", "running", "completed", "interrupted"}:
            raise SessionError(f"invalid session status: {status}")
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE sessions SET messages = ?, status = ?, updated_at = ?, error = ? WHERE id = ?",
                (json.dumps(messages, ensure_ascii=False), status, now, error, identifier),
            )
        if cursor.rowcount != 1:
            raise SessionError(f"unknown session: {identifier}")

    def delete(self, identifier: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM sessions WHERE id = ?", (identifier,))
        if cursor.rowcount != 1:
            raise SessionError(f"unknown session: {identifier}")
