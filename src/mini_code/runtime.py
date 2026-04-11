from __future__ import annotations

import json
import time
from typing import Any, Callable

from .config import AppConfig
from .features.background import BackgroundManager
from .features.skills import SkillLoader
from .features.tasks import TaskManager
from .features.team import MessageBus, TeammateManager, VALID_MSG_TYPES
from .features.todo import TodoManager
from .llm import AnthropicProvider, iter_tool_uses, normalize_content_blocks
from .prompting import build_system_prompt
from .tools.files import run_bash, run_edit, run_read, run_write
from .tools.subagent import SubagentRunner

PRESERVE_RESULT_TOOLS = {"read_file"}


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    return len(json.dumps(messages, default=str)) // 4


def microcompact(messages: list[dict[str, Any]], keep_recent: int = 3) -> None:
    tool_results: list[dict[str, Any]] = []
    for message in messages:
        if message["role"] == "user" and isinstance(message.get("content"), list):
            for part in message["content"]:
                if isinstance(part, dict) and part.get("type") == "tool_result":
                    tool_results.append(part)
    if len(tool_results) <= keep_recent:
        return
    tool_name_map: dict[str, str] = {}
    for message in messages:
        if message["role"] != "assistant":
            continue
        content = message.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tool_name_map[str(block.get("id", ""))] = str(block.get("name", "unknown"))
    for part in tool_results[:-keep_recent]:
        content = part.get("content")
        if not isinstance(content, str) or len(content) <= 100:
            continue
        tool_name = tool_name_map.get(str(part.get("tool_use_id", "")), "unknown")
        if tool_name in PRESERVE_RESULT_TOOLS:
            continue
        part["content"] = f"[Previous: used {tool_name}]"


def auto_compact(
    messages: list[dict[str, Any]],
    provider: AnthropicProvider,
    config: AppConfig,
    focus: str | None = None,
) -> list[dict[str, Any]]:
    config.paths.transcripts_dir.mkdir(parents=True, exist_ok=True)
    path = config.paths.transcripts_dir / f"transcript_{int(time.time())}.jsonl"
    with path.open("w") as handle:
        for message in messages:
            handle.write(json.dumps(message, default=str) + "\n")
    conversation_text = json.dumps(messages, default=str)[:80000]
    prompt = (
        "Summarize this conversation for continuity. Structure your summary:\n"
        "1) Task overview: core request, success criteria, constraints\n"
        "2) Current state: completed work, files touched, artifacts created\n"
        "3) Key decisions and discoveries: constraints, errors, failed approaches\n"
        "4) Next steps: remaining actions, blockers, priority order\n"
        "5) Context to preserve: user preferences, domain details, commitments\n"
        "Be concise but preserve critical details.\n"
    )
    if focus:
        prompt += f"\nPay special attention to: {focus}\n"
    response = provider.create_message(
        system=None,
        messages=[{"role": "user", "content": prompt + "\n" + conversation_text}],
        tools=None,
        max_tokens=4000,
    )
    summary_blocks = normalize_content_blocks(getattr(response, "content", []))
    summary = "".join(
        str(block.get("text", "")) for block in summary_blocks if block.get("type") == "text"
    )
    continuation = (
        "This session is being continued from a previous conversation that ran out "
        "of context. The summary below covers the earlier portion of the conversation.\n\n"
        f"{summary}\n\n"
        "Please continue the conversation from where we left it off without asking "
        "the user any further questions."
    )
    return [{"role": "user", "content": continuation}]


class AgentRuntime:
    def __init__(
        self,
        config: AppConfig,
        provider: AnthropicProvider,
        todo_manager: TodoManager,
        skill_loader: SkillLoader,
        task_manager: TaskManager,
        background_manager: BackgroundManager,
        message_bus: MessageBus,
        teammate_manager: TeammateManager,
    ):
        self.config = config
        self.provider = provider
        self.todo_manager = todo_manager
        self.skill_loader = skill_loader
        self.task_manager = task_manager
        self.background_manager = background_manager
        self.message_bus = message_bus
        self.teammate_manager = teammate_manager
        self.subagent_runner = SubagentRunner(config, provider)
        self.rounds_without_todo = 0

    def build_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "bash",
                "description": "Run a shell command.",
                "input_schema": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            },
            {
                "name": "read_file",
                "description": "Read file contents.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "write_file",
                "description": "Write content to file.",
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
                "description": "Replace exact text in file.",
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
                "name": "TodoWrite",
                "description": "Update task tracking list.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "content": {"type": "string"},
                                    "status": {
                                        "type": "string",
                                        "enum": ["pending", "in_progress", "completed"],
                                    },
                                    "active_form": {"type": "string"},
                                },
                                "required": ["content", "status", "active_form"],
                            },
                        }
                    },
                    "required": ["items"],
                },
            },
            {
                "name": "task",
                "description": "Spawn a subagent for isolated exploration or work.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "agent_type": {
                            "type": "string",
                            "enum": ["Explore", "general-purpose"],
                        },
                    },
                    "required": ["prompt"],
                },
            },
            {
                "name": "load_skill",
                "description": "Load specialized knowledge by name.",
                "input_schema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            },
            {
                "name": "compress",
                "description": "Manually compress conversation context.",
                "input_schema": {
                    "type": "object",
                    "properties": {"focus": {"type": "string"}},
                },
            },
            {
                "name": "background_run",
                "description": "Run command in background thread.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "timeout": {"type": "integer"},
                    },
                    "required": ["command"],
                },
            },
            {
                "name": "check_background",
                "description": "Check background task status.",
                "input_schema": {
                    "type": "object",
                    "properties": {"task_id": {"type": "string"}},
                },
            },
            {
                "name": "task_create",
                "description": "Create a persistent file task.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["subject"],
                },
            },
            {
                "name": "task_get",
                "description": "Get task details by ID.",
                "input_schema": {
                    "type": "object",
                    "properties": {"task_id": {"type": "integer"}},
                    "required": ["task_id"],
                },
            },
            {
                "name": "task_update",
                "description": "Update task status or dependencies.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "integer"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed", "deleted"],
                        },
                        "add_blocked_by": {
                            "type": "array",
                            "items": {"type": "integer"},
                        },
                        "add_blocks": {
                            "type": "array",
                            "items": {"type": "integer"},
                        },
                    },
                    "required": ["task_id"],
                },
            },
            {
                "name": "task_list",
                "description": "List all tasks.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "spawn_teammate",
                "description": "Spawn a persistent autonomous teammate.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "role": {"type": "string"},
                        "prompt": {"type": "string"},
                    },
                    "required": ["name", "role", "prompt"],
                },
            },
            {
                "name": "list_teammates",
                "description": "List all teammates.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "send_message",
                "description": "Send a message to a teammate.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string"},
                        "content": {"type": "string"},
                        "msg_type": {
                            "type": "string",
                            "enum": sorted(VALID_MSG_TYPES),
                        },
                    },
                    "required": ["to", "content"],
                },
            },
            {
                "name": "read_inbox",
                "description": "Read and drain the lead's inbox.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "broadcast",
                "description": "Send message to all teammates.",
                "input_schema": {
                    "type": "object",
                    "properties": {"content": {"type": "string"}},
                    "required": ["content"],
                },
            },
            {
                "name": "shutdown_request",
                "description": "Request a teammate to shut down.",
                "input_schema": {
                    "type": "object",
                    "properties": {"teammate": {"type": "string"}},
                    "required": ["teammate"],
                },
            },
            {
                "name": "plan_approval",
                "description": "Approve or reject a teammate's plan.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "request_id": {"type": "string"},
                        "approve": {"type": "boolean"},
                        "feedback": {"type": "string"},
                    },
                    "required": ["request_id", "approve"],
                },
            },
            {
                "name": "idle",
                "description": "Enter idle state.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "claim_task",
                "description": "Claim a task from the board.",
                "input_schema": {
                    "type": "object",
                    "properties": {"task_id": {"type": "integer"}},
                    "required": ["task_id"],
                },
            },
        ]

    def build_tool_handlers(self) -> dict[str, Callable[..., str]]:
        return {
            "bash": lambda **kw: run_bash(self.config, kw["command"], kw.get("tool_use_id", "")),
            "read_file": lambda **kw: run_read(
                self.config,
                kw["path"],
                kw.get("tool_use_id", ""),
                kw.get("limit"),
            ),
            "write_file": lambda **kw: run_write(self.config, kw["path"], kw["content"]),
            "edit_file": lambda **kw: run_edit(
                self.config,
                kw["path"],
                kw["old_text"],
                kw["new_text"],
            ),
            "TodoWrite": lambda **kw: self.todo_manager.update(kw["items"]),
            "task": lambda **kw: self.subagent_runner.run(
                kw["prompt"], kw.get("agent_type", "Explore")
            ),
            "load_skill": lambda **kw: self.skill_loader.load(kw["name"]),
            "compress": lambda **kw: "Compressing...",
            "background_run": lambda **kw: self.background_manager.run(
                kw["command"], kw.get("timeout", 120)
            ),
            "check_background": lambda **kw: self.background_manager.check(kw.get("task_id")),
            "task_create": lambda **kw: self.task_manager.create(
                kw["subject"], kw.get("description", "")
            ),
            "task_get": lambda **kw: self.task_manager.get(int(kw["task_id"])),
            "task_update": lambda **kw: self.task_manager.update(
                int(kw["task_id"]),
                kw.get("status"),
                kw.get("add_blocked_by"),
                kw.get("add_blocks"),
            ),
            "task_list": lambda **kw: self.task_manager.list_all(),
            "spawn_teammate": lambda **kw: self.teammate_manager.spawn(
                kw["name"], kw["role"], kw["prompt"]
            ),
            "list_teammates": lambda **kw: self.teammate_manager.list_all(),
            "send_message": lambda **kw: self.message_bus.send(
                "lead", kw["to"], kw["content"], kw.get("msg_type", "message")
            ),
            "read_inbox": lambda **kw: json.dumps(self.message_bus.read_inbox("lead"), indent=2),
            "broadcast": lambda **kw: self.message_bus.broadcast(
                "lead", kw["content"], self.teammate_manager.member_names()
            ),
            "shutdown_request": lambda **kw: self.teammate_manager.shutdown_registry.request_shutdown(
                kw["teammate"], self.message_bus
            ),
            "plan_approval": lambda **kw: self.teammate_manager.plan_registry.review(
                kw["request_id"],
                kw["approve"],
                kw.get("feedback", ""),
                self.message_bus,
            ),
            "idle": lambda **kw: "Lead does not idle.",
            "claim_task": lambda **kw: self.task_manager.claim(int(kw["task_id"]), "lead"),
        }

    def _system_prompt(self, reminder: str | None = None) -> str:
        system = build_system_prompt(self.skill_loader.descriptions(), self.config.workdir)
        if reminder:
            system += f"\n{reminder}"
        return system

    def run_turn(self, history: list[dict[str, Any]]) -> bool:
        microcompact(history, keep_recent=self.config.keep_recent_tool_results)
        if estimate_tokens(history) > self.config.token_threshold:
            history[:] = auto_compact(history, self.provider, self.config)
        notifications = self.background_manager.drain()
        if notifications:
            text = "\n".join(
                f"[bg:{item['task_id']}] {item['status']}: {item['result']}"
                for item in notifications
            )
            history.append(
                {
                    "role": "user",
                    "content": f"<background-results>\n{text}\n</background-results>",
                }
            )
            history.append({"role": "assistant", "content": "Noted background results."})
        inbox = self.message_bus.read_inbox("lead")
        if inbox:
            history.append({"role": "user", "content": f"<inbox>{json.dumps(inbox, indent=2)}</inbox>"})
            history.append({"role": "assistant", "content": "Noted inbox messages."})
        reminder = None
        if self.todo_manager.has_open_items() and self.rounds_without_todo >= 3:
            reminder = "<reminder>Update your todos.</reminder>"
        response = self.provider.create_message(
            system=self._system_prompt(reminder=reminder),
            messages=history,
            tools=self.build_tools(),
            max_tokens=8000,
        )
        assistant_content = normalize_content_blocks(getattr(response, "content", []))
        history.append({"role": "assistant", "content": assistant_content})
        if getattr(response, "stop_reason", None) != "tool_use":
            return False
        results: list[dict[str, Any]] = []
        handlers = self.build_tool_handlers()
        used_todo = False
        manual_compress = False
        compact_focus = None
        for block in iter_tool_uses(assistant_content):
            if block["name"] == "compress":
                manual_compress = True
                compact_focus = (block.get("input") or {}).get("focus")
            handler = handlers.get(block["name"])
            try:
                tool_input = dict(block.get("input") or {})
                tool_input["tool_use_id"] = block["id"]
                output = handler(**tool_input) if handler else f"Unknown tool: {block['name']}"
            except Exception as exc:
                output = f"Error: {exc}"
            results.append({"type": "tool_result", "tool_use_id": block["id"], "content": str(output)})
            if block["name"] == "TodoWrite":
                used_todo = True
        self.rounds_without_todo = 0 if used_todo else self.rounds_without_todo + 1
        history.append({"role": "user", "content": results})
        if manual_compress:
            history[:] = auto_compact(history, self.provider, self.config, focus=compact_focus)
        return True

    def agent_loop(self, history: list[dict[str, Any]]) -> None:
        while self.run_turn(history):
            continue
