from __future__ import annotations

import json

from ..config import WorkspacePaths
from ..models import TaskRecord


class TaskManager:
    def __init__(self, paths: WorkspacePaths):
        self.paths = paths
        self.paths.tasks_dir.mkdir(parents=True, exist_ok=True)

    def _task_path(self, task_id: int):
        return self.paths.tasks_dir / f"task_{task_id}.json"

    def _next_id(self) -> int:
        ids = []
        for file in self.paths.tasks_dir.glob("task_*.json"):
            parts = file.stem.split("_")
            if len(parts) == 2 and parts[1].isdigit():
                ids.append(int(parts[1]))
        return max(ids, default=0) + 1

    def _load_record(self, task_id: int) -> TaskRecord:
        path = self._task_path(task_id)
        if not path.exists():
            raise ValueError(f"Task {task_id} not found")
        return TaskRecord.from_dict(json.loads(path.read_text()))

    def _save_record(self, record: TaskRecord) -> None:
        self._task_path(record.id).write_text(json.dumps(record.to_dict(), indent=2))

    def list_records(self) -> list[TaskRecord]:
        records = []
        for file in sorted(self.paths.tasks_dir.glob("task_*.json")):
            records.append(TaskRecord.from_dict(json.loads(file.read_text())))
        return records

    def create(self, subject: str, description: str = "") -> str:
        record = TaskRecord(id=self._next_id(), subject=subject, description=description)
        self._save_record(record)
        return json.dumps(record.to_dict(), indent=2)

    def get(self, task_id: int) -> str:
        return json.dumps(self._load_record(task_id).to_dict(), indent=2)

    def update(
        self,
        task_id: int,
        status: str | None = None,
        add_blocked_by: list[int] | None = None,
        add_blocks: list[int] | None = None,
    ) -> str:
        record = self._load_record(task_id)
        if status:
            record.status = status
            if status == "completed":
                for other in self.list_records():
                    if record.id in other.blocked_by:
                        other.blocked_by.remove(record.id)
                        self._save_record(other)
            if status == "deleted":
                self._task_path(task_id).unlink(missing_ok=True)
                return f"Task {task_id} deleted"
        if add_blocked_by:
            record.blocked_by = sorted(set(record.blocked_by + [int(item) for item in add_blocked_by]))
        if add_blocks:
            record.blocks = sorted(set(record.blocks + [int(item) for item in add_blocks]))
        self._save_record(record)
        return json.dumps(record.to_dict(), indent=2)

    def list_all(self) -> str:
        records = self.list_records()
        if not records:
            return "No tasks."
        lines = []
        for task in records:
            marker = {
                "pending": "[ ]",
                "in_progress": "[>]",
                "completed": "[x]",
            }.get(task.status, "[?]")
            owner = f" @{task.owner}" if task.owner else ""
            blocked = f" (blocked by: {task.blocked_by})" if task.blocked_by else ""
            lines.append(f"{marker} #{task.id}: {task.subject}{owner}{blocked}")
        return "\n".join(lines)

    def claim(self, task_id: int, owner: str) -> str:
        record = self._load_record(task_id)
        record.owner = owner
        record.status = "in_progress"
        self._save_record(record)
        return f"Claimed task #{task_id} for {owner}"
