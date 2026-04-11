from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class TodoItem:
    content: str
    status: str
    active_form: str

    def to_dict(self) -> dict[str, str]:
        return {
            "content": self.content,
            "status": self.status,
            "active_form": self.active_form,
        }


@dataclass(slots=True)
class TaskRecord:
    id: int
    subject: str
    description: str = ""
    status: str = "pending"
    owner: str | None = None
    blocked_by: list[int] = field(default_factory=list)
    blocks: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskRecord":
        return cls(
            id=int(data["id"]),
            subject=str(data["subject"]),
            description=str(data.get("description", "")),
            status=str(data.get("status", "pending")),
            owner=data.get("owner"),
            blocked_by=[int(item) for item in data.get("blocked_by", [])],
            blocks=[int(item) for item in data.get("blocks", [])],
        )


@dataclass(slots=True)
class BackgroundTaskRecord:
    id: str
    status: str
    command: str
    result: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TeamMessage:
    type: str
    sender: str
    content: str
    timestamp: float
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "type": self.type,
            "from": self.sender,
            "content": self.content,
            "timestamp": self.timestamp,
        }
        payload.update(self.extra)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TeamMessage":
        reserved = {"type", "from", "content", "timestamp"}
        extra = {key: value for key, value in data.items() if key not in reserved}
        return cls(
            type=str(data["type"]),
            sender=str(data["from"]),
            content=str(data["content"]),
            timestamp=float(data["timestamp"]),
            extra=extra,
        )


@dataclass(slots=True)
class ToolResult:
    tool_use_id: str
    content: str
    type: str = "tool_result"

    def to_dict(self) -> dict[str, str]:
        return {
            "type": self.type,
            "tool_use_id": self.tool_use_id,
            "content": self.content,
        }
