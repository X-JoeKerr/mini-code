from __future__ import annotations

import subprocess
import threading
import uuid
from queue import Queue

from ..config import AppConfig
from ..models import BackgroundTaskRecord


class BackgroundManager:
    def __init__(self, config: AppConfig):
        self.config = config
        self.tasks: dict[str, BackgroundTaskRecord] = {}
        self.notifications: Queue[dict[str, str]] = Queue()

    def run(self, command: str, timeout: int = 120) -> str:
        task_id = str(uuid.uuid4())[:8]
        self.tasks[task_id] = BackgroundTaskRecord(
            id=task_id,
            status="running",
            command=command,
            result=None,
        )
        thread = threading.Thread(
            target=self._exec,
            args=(task_id, command, timeout),
            daemon=True,
        )
        thread.start()
        return f"Background task {task_id} started: {command[:80]}"

    def _exec(self, task_id: str, command: str, timeout: int) -> None:
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.config.workdir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = (result.stdout + result.stderr).strip()
            output = (output or "(no output)")[: self.config.max_tool_output_chars]
            self.tasks[task_id].status = "completed"
            self.tasks[task_id].result = output
        except Exception as exc:
            self.tasks[task_id].status = "error"
            self.tasks[task_id].result = str(exc)
        self.notifications.put(
            {
                "task_id": task_id,
                "status": self.tasks[task_id].status,
                "result": (self.tasks[task_id].result or "")[:500],
            }
        )

    def check(self, task_id: str | None = None) -> str:
        if task_id:
            task = self.tasks.get(task_id)
            if not task:
                return f"Unknown: {task_id}"
            result = task.result or "(running)"
            return f"[{task.status}] {result}"
        if not self.tasks:
            return "No bg tasks."
        return "\n".join(
            f"{key}: [{task.status}] {task.command[:60]}"
            for key, task in self.tasks.items()
        )

    def drain(self) -> list[dict[str, str]]:
        notifications: list[dict[str, str]] = []
        while not self.notifications.empty():
            notifications.append(self.notifications.get_nowait())
        return notifications
