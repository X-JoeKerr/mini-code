from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..models import TodoItem

SCHEMA_VERSION = 1
SESSION_PREVIEW_LIMIT = 80


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return json.loads(json.dumps(history, ensure_ascii=False, default=str))


def _normalize_todo_items(todo_items: list[dict[str, Any]] | list[TodoItem]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in todo_items:
        if isinstance(item, TodoItem):
            normalized.append(item.to_dict())
            continue
        normalized.append(
            {
                "content": str(item.get("content", "")),
                "status": str(item.get("status", "")),
                "active_form": str(item.get("active_form", "")),
            }
        )
    return normalized


def _build_preview(history: list[dict[str, Any]]) -> str:
    for message in history:
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        preview = " ".join(content.split())
        if not preview:
            continue
        if len(preview) > SESSION_PREVIEW_LIMIT:
            return f"{preview[: SESSION_PREVIEW_LIMIT - 3]}..."
        return preview
    return "(no user message)"


@dataclass(slots=True)
class SessionSummary:
    session_id: str
    created_at: str
    updated_at: str
    preview: str
    message_count: int


@dataclass(slots=True)
class SessionSnapshot:
    session_id: str
    created_at: str
    updated_at: str
    history: list[dict[str, Any]]
    todo_items: list[TodoItem]
    preview: str
    message_count: int


class SessionManager:
    def __init__(self, sessions_dir: Path):
        self.sessions_dir = sessions_dir
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        session_id: str,
        history: list[dict[str, Any]],
        todo_items: list[dict[str, Any]] | list[TodoItem],
    ) -> None:
        if not history:
            return
        path = self._path_for(session_id)
        created_at = _utc_now()
        if path.exists():
            try:
                existing = self._read_payload(path)
            except ValueError:
                existing = None
            if existing is not None:
                created_at = str(existing["created_at"])
        payload = {
            "schema_version": SCHEMA_VERSION,
            "session_id": session_id,
            "created_at": created_at,
            "updated_at": _utc_now(),
            "history": _normalize_history(history),
            "todo_items": _normalize_todo_items(todo_items),
        }
        payload["preview"] = _build_preview(payload["history"])
        payload["message_count"] = len(payload["history"])
        temp_path = path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)

    def load(self, session_id: str) -> SessionSnapshot:
        payload = self._read_payload(self._path_for(session_id))
        return self._snapshot_from_payload(payload)

    def list_all(self) -> list[SessionSummary]:
        summaries: list[SessionSummary] = []
        for path in sorted(self.sessions_dir.glob("session_*.json")):
            try:
                payload = self._read_payload(path)
            except ValueError:
                continue
            summaries.append(
                SessionSummary(
                    session_id=str(payload["session_id"]),
                    created_at=str(payload["created_at"]),
                    updated_at=str(payload["updated_at"]),
                    preview=str(payload["preview"]),
                    message_count=int(payload["message_count"]),
                )
            )
        summaries.sort(key=lambda item: item.updated_at, reverse=True)
        return summaries

    def _path_for(self, session_id: str) -> Path:
        return self.sessions_dir / f"session_{session_id}.json"

    def _read_payload(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise ValueError(f"Unknown session: {path.stem}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid session file: {path.name}") from exc
        required = {
            "schema_version",
            "session_id",
            "created_at",
            "updated_at",
            "history",
            "todo_items",
            "preview",
            "message_count",
        }
        if not isinstance(payload, dict) or not required.issubset(payload):
            raise ValueError(f"Incomplete session file: {path.name}")
        if int(payload["schema_version"]) != SCHEMA_VERSION:
            raise ValueError(f"Unsupported session schema: {path.name}")
        if not isinstance(payload["history"], list) or not isinstance(payload["todo_items"], list):
            raise ValueError(f"Invalid session content: {path.name}")
        return payload

    @staticmethod
    def _snapshot_from_payload(payload: dict[str, Any]) -> SessionSnapshot:
        todo_items = [TodoItem(**item) for item in payload["todo_items"]]
        return SessionSnapshot(
            session_id=str(payload["session_id"]),
            created_at=str(payload["created_at"]),
            updated_at=str(payload["updated_at"]),
            history=list(payload["history"]),
            todo_items=todo_items,
            preview=str(payload["preview"]),
            message_count=int(payload["message_count"]),
        )
