from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from ..config import AppConfig
from ..llm import AnthropicProvider, iter_tool_uses, normalize_content_blocks
from ..models import TeamMessage
from ..tools.files import run_bash, run_edit, run_read, run_write
from .tasks import TaskManager

VALID_MSG_TYPES = {
    "message",
    "broadcast",
    "shutdown_request",
    "shutdown_response",
    "plan_approval_response",
}


class MessageBus:
    def __init__(self, inbox_dir: Path):
        self.inbox_dir = inbox_dir
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

    def send(
        self,
        sender: str,
        to: str,
        content: str,
        msg_type: str = "message",
        extra: dict[str, Any] | None = None,
    ) -> str:
        if msg_type not in VALID_MSG_TYPES:
            raise ValueError(f"Invalid message type: {msg_type}")
        message = TeamMessage(
            type=msg_type,
            sender=sender,
            content=content,
            timestamp=time.time(),
            extra=extra or {},
        )
        with (self.inbox_dir / f"{to}.jsonl").open("a") as handle:
            handle.write(json.dumps(message.to_dict()) + "\n")
        return f"Sent {msg_type} to {to}"

    def read_inbox(self, name: str) -> list[dict[str, Any]]:
        path = self.inbox_dir / f"{name}.jsonl"
        if not path.exists():
            return []
        messages = [
            TeamMessage.from_dict(json.loads(line)).to_dict()
            for line in path.read_text().splitlines()
            if line.strip()
        ]
        path.write_text("")
        return messages

    def broadcast(self, sender: str, content: str, names: list[str]) -> str:
        count = 0
        for name in names:
            if name == sender:
                continue
            self.send(sender, name, content, "broadcast")
            count += 1
        return f"Broadcast to {count} teammates"


class ShutdownRegistry:
    def __init__(self):
        self.requests: dict[str, dict[str, str]] = {}

    def request_shutdown(self, teammate: str, bus: MessageBus, sender: str = "lead") -> str:
        request_id = str(uuid.uuid4())[:8]
        self.requests[request_id] = {"target": teammate, "status": "pending"}
        bus.send(
            sender,
            teammate,
            "Please shut down.",
            "shutdown_request",
            {"request_id": request_id},
        )
        return f"Shutdown request {request_id} sent to '{teammate}'"


class PlanApprovalRegistry:
    def __init__(self):
        self.requests: dict[str, dict[str, str]] = {}

    def register_request(self, sender: str, content: str = "") -> str:
        request_id = str(uuid.uuid4())[:8]
        self.requests[request_id] = {"from": sender, "status": "pending", "content": content}
        return request_id

    def review(
        self,
        request_id: str,
        approve: bool,
        feedback: str,
        bus: MessageBus,
        sender: str = "lead",
    ) -> str:
        request = self.requests.get(request_id)
        if not request:
            return f"Error: Unknown plan request_id '{request_id}'"
        request["status"] = "approved" if approve else "rejected"
        bus.send(
            sender,
            request["from"],
            feedback,
            "plan_approval_response",
            {
                "request_id": request_id,
                "approve": approve,
                "feedback": feedback,
            },
        )
        return f"Plan {request['status']} for '{request['from']}'"


class TeammateManager:
    def __init__(
        self,
        config: AppConfig,
        provider: AnthropicProvider,
        task_manager: TaskManager,
        message_bus: MessageBus,
        shutdown_registry: ShutdownRegistry | None = None,
        plan_registry: PlanApprovalRegistry | None = None,
    ):
        self.config = config
        self.provider = provider
        self.task_manager = task_manager
        self.message_bus = message_bus
        self.shutdown_registry = shutdown_registry or ShutdownRegistry()
        self.plan_registry = plan_registry or PlanApprovalRegistry()
        self.config.paths.team_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.config.paths.team_dir / "config.json"
        self.config_state = self._load()
        self.threads: dict[str, threading.Thread] = {}

    def _load(self) -> dict[str, Any]:
        if self.config_path.exists():
            return json.loads(self.config_path.read_text())
        return {"team_name": "default", "members": []}

    def _save(self) -> None:
        self.config_path.write_text(json.dumps(self.config_state, indent=2))

    def _find(self, name: str) -> dict[str, Any] | None:
        for member in self.config_state["members"]:
            if member["name"] == name:
                return member
        return None

    def _set_status(self, name: str, status: str) -> None:
        member = self._find(name)
        if member:
            member["status"] = status
            self._save()

    def spawn(self, name: str, role: str, prompt: str) -> str:
        member = self._find(name)
        if member:
            if member["status"] not in ("idle", "shutdown"):
                return f"Error: '{name}' is currently {member['status']}"
            member["status"] = "working"
            member["role"] = role
        else:
            member = {"name": name, "role": role, "status": "working"}
            self.config_state["members"].append(member)
        self._save()
        thread = threading.Thread(target=self._loop, args=(name, role, prompt), daemon=True)
        self.threads[name] = thread
        thread.start()
        return f"Spawned '{name}' (role: {role})"

    def _loop(self, name: str, role: str, prompt: str) -> None:
        team_name = self.config_state["team_name"]
        system_prompt = (
            f"You are '{name}', role: {role}, team: {team_name}, at {self.config.workdir}. "
            "Use idle when done with current work. You may auto-claim tasks."
        )
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        tools = [
            {
                "name": "bash",
                "description": "Run command.",
                "input_schema": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            },
            {
                "name": "read_file",
                "description": "Read file.",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
            {
                "name": "write_file",
                "description": "Write file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
            {
                "name": "edit_file",
                "description": "Edit file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "old_text": {"type": "string"},
                        "new_text": {"type": "string"},
                    },
                    "required": ["path", "old_text", "new_text"],
                },
            },
            {
                "name": "send_message",
                "description": "Send message.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["to", "content"],
                },
            },
            {
                "name": "idle",
                "description": "Signal no more work.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "claim_task",
                "description": "Claim task by ID.",
                "input_schema": {
                    "type": "object",
                    "properties": {"task_id": {"type": "integer"}},
                    "required": ["task_id"],
                },
            },
        ]
        while True:
            for _ in range(50):
                inbox = self.message_bus.read_inbox(name)
                for message in inbox:
                    if message.get("type") == "shutdown_request":
                        self._set_status(name, "shutdown")
                        return
                    messages.append({"role": "user", "content": json.dumps(message)})
                try:
                    response = self.provider.create_message(
                        system=system_prompt,
                        messages=messages,
                        tools=tools,
                        max_tokens=8000,
                    )
                except Exception:
                    self._set_status(name, "shutdown")
                    return
                assistant_content = normalize_content_blocks(getattr(response, "content", []))
                messages.append({"role": "assistant", "content": assistant_content})
                if getattr(response, "stop_reason", None) != "tool_use":
                    break
                results = []
                idle_requested = False
                for block in iter_tool_uses(assistant_content):
                    if block["name"] == "idle":
                        idle_requested = True
                        output = "Entering idle phase."
                    elif block["name"] == "claim_task":
                        output = self.task_manager.claim(int(block["input"]["task_id"]), name)
                    elif block["name"] == "send_message":
                        output = self.message_bus.send(
                            name,
                            block["input"]["to"],
                            block["input"]["content"],
                        )
                    else:
                        output = {
                            "bash": lambda: run_bash(self.config, block["input"]["command"]),
                            "read_file": lambda: run_read(self.config, block["input"]["path"]),
                            "write_file": lambda: run_write(
                                self.config,
                                block["input"]["path"],
                                block["input"]["content"],
                            ),
                            "edit_file": lambda: run_edit(
                                self.config,
                                block["input"]["path"],
                                block["input"]["old_text"],
                                block["input"]["new_text"],
                            ),
                        }.get(block["name"], lambda: "Unknown")()
                    results.append(
                        {"type": "tool_result", "tool_use_id": block["id"], "content": str(output)}
                    )
                messages.append({"role": "user", "content": results})
                if idle_requested:
                    break
            self._set_status(name, "idle")
            resume = False
            polls = max(self.config.idle_timeout // max(self.config.poll_interval, 1), 1)
            for _ in range(polls):
                time.sleep(self.config.poll_interval)
                inbox = self.message_bus.read_inbox(name)
                if inbox:
                    for message in inbox:
                        if message.get("type") == "shutdown_request":
                            self._set_status(name, "shutdown")
                            return
                        messages.append({"role": "user", "content": json.dumps(message)})
                    resume = True
                    break
                unclaimed = [
                    task
                    for task in self.task_manager.list_records()
                    if task.status == "pending" and not task.owner and not task.blocked_by
                ]
                if unclaimed:
                    task = unclaimed[0]
                    self.task_manager.claim(task.id, name)
                    if len(messages) <= 3:
                        messages.insert(
                            0,
                            {
                                "role": "user",
                                "content": (
                                    f"<identity>You are '{name}', role: {role}, "
                                    f"team: {team_name}.</identity>"
                                ),
                            },
                        )
                        messages.insert(
                            1,
                            {"role": "assistant", "content": "I am continuing my assigned work."},
                        )
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"<auto-claimed>Task #{task.id}: {task.subject}\n"
                                f"{task.description}</auto-claimed>"
                            ),
                        }
                    )
                    messages.append(
                        {
                            "role": "assistant",
                            "content": f"Claimed task #{task.id}. Working on it.",
                        }
                    )
                    resume = True
                    break
            if not resume:
                self._set_status(name, "shutdown")
                return
            self._set_status(name, "working")

    def list_all(self) -> str:
        if not self.config_state["members"]:
            return "No teammates."
        lines = [f"Team: {self.config_state['team_name']}"]
        for member in self.config_state["members"]:
            lines.append(f"  {member['name']} ({member['role']}): {member['status']}")
        return "\n".join(lines)

    def member_names(self) -> list[str]:
        return [member["name"] for member in self.config_state["members"]]
