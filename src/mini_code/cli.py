from __future__ import annotations

import argparse
import json
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, TextIO

from .config import AppConfig
from .features.background import BackgroundManager
from .features.sessions import SessionManager
from .features.skills import SkillLoader
from .features.tasks import TaskManager
from .features.team import MessageBus, PlanApprovalRegistry, ShutdownRegistry, TeammateManager
from .features.todo import TodoManager
from .llm import AnthropicProvider, extract_text, iter_tool_uses
from .runtime import AgentRuntime, auto_compact

TOOL_CALL_PREVIEW_LIMIT = 80


@dataclass
class AppContext:
    config: AppConfig
    provider: AnthropicProvider
    todo_manager: TodoManager
    session_manager: SessionManager
    skill_loader: SkillLoader
    task_manager: TaskManager
    background_manager: BackgroundManager
    message_bus: MessageBus
    teammate_manager: TeammateManager
    runtime: AgentRuntime


class WaitingPlaceholder:
    FRAMES = ("", ".", "..", "...")
    LABELS = {
        "waiting_request": "Sending",
        "waiting_model": "Thinking",
        "waiting_tool": "Working",
    }

    def __init__(
        self,
        stream: TextIO | None = None,
        *,
        enabled: bool | None = None,
        interval: float = 0.12,
    ):
        self.stream = stream or sys.stdout
        self.enabled = enabled if enabled is not None else bool(getattr(self.stream, "isatty", lambda: False)())
        self.interval = interval
        self._message = ""
        self._frame_index = 0
        self._last_width = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def update(self, state: str, detail: str | None = None) -> None:
        if not self.enabled:
            return
        message = self.LABELS.get(state, state)
        if detail and state == "waiting_tool":
            message = f"{message}: {detail}"
        with self._lock:
            self._message = message
            self._frame_index = 0
            self._render_locked()
            if self._thread is None or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(target=self._animate, daemon=True)
                self._thread.start()

    def clear(self) -> None:
        if not self.enabled:
            return
        thread = self._thread
        self._stop.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout=self.interval * 2 + 0.1)
        with self._lock:
            self._thread = None
            self._message = ""
            blank = " " * self._last_width
            if blank:
                self.stream.write(f"\r{blank}\r")
                self.stream.flush()
            self._last_width = 0
            self._frame_index = 0

    def _animate(self) -> None:
        while not self._stop.wait(self.interval):
            with self._lock:
                if not self._message:
                    continue
                self._frame_index = (self._frame_index + 1) % len(self.FRAMES)
                self._render_locked()

    def _render_locked(self) -> None:
        suffix = self.FRAMES[self._frame_index]
        line = f"{self._message}{suffix}"
        padding = max(0, self._last_width - len(line))
        self.stream.write(f"\r{line}{' ' * padding}")
        self.stream.flush()
        self._last_width = len(line)


def build_app(workdir: Path | None = None, session_id: str | None = None) -> AppContext:
    config = AppConfig.from_env(workdir=workdir, session_id=session_id)
    provider = AnthropicProvider(config)
    todo_manager = TodoManager()
    session_manager = SessionManager(config.paths.sessions_dir)
    skill_loader = SkillLoader(config.paths.skills_dir)
    task_manager = TaskManager(config.paths)
    background_manager = BackgroundManager(config)
    message_bus = MessageBus(config.paths.inbox_dir)
    shutdown_registry = ShutdownRegistry()
    plan_registry = PlanApprovalRegistry()
    teammate_manager = TeammateManager(
        config=config,
        provider=provider,
        task_manager=task_manager,
        message_bus=message_bus,
        shutdown_registry=shutdown_registry,
        plan_registry=plan_registry,
    )
    runtime = AgentRuntime(
        config=config,
        provider=provider,
        todo_manager=todo_manager,
        skill_loader=skill_loader,
        task_manager=task_manager,
        background_manager=background_manager,
        message_bus=message_bus,
        teammate_manager=teammate_manager,
    )
    return AppContext(
        config=config,
        provider=provider,
        todo_manager=todo_manager,
        session_manager=session_manager,
        skill_loader=skill_loader,
        task_manager=task_manager,
        background_manager=background_manager,
        message_bus=message_bus,
        teammate_manager=teammate_manager,
        runtime=runtime,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mini-code")
    parser.add_argument("--workdir", type=Path, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("chat")

    tasks = subparsers.add_parser("tasks")
    task_sub = tasks.add_subparsers(dest="tasks_command", required=True)
    task_sub.add_parser("list")
    task_get = task_sub.add_parser("get")
    task_get.add_argument("task_id", type=int)
    task_create = task_sub.add_parser("create")
    task_create.add_argument("subject")
    task_create.add_argument("--description", default="")
    task_update = task_sub.add_parser("update")
    task_update.add_argument("task_id", type=int)
    task_update.add_argument("--status")
    task_update.add_argument("--add-blocked-by", nargs="*", type=int, default=None)
    task_update.add_argument("--add-blocks", nargs="*", type=int, default=None)

    team = subparsers.add_parser("team")
    team_sub = team.add_subparsers(dest="team_command", required=True)
    team_sub.add_parser("list")
    team_spawn = team_sub.add_parser("spawn")
    team_spawn.add_argument("name")
    team_spawn.add_argument("role")
    team_spawn.add_argument("prompt")
    team_send = team_sub.add_parser("send")
    team_send.add_argument("to")
    team_send.add_argument("content")
    team_send.add_argument("--msg-type", default="message")
    team_sub.add_parser("inbox")

    bg = subparsers.add_parser("bg")
    bg_sub = bg.add_subparsers(dest="bg_command", required=True)
    bg_sub.add_parser("list")
    bg_get = bg_sub.add_parser("get")
    bg_get.add_argument("task_id")

    return parser


def run_chat(app: AppContext) -> int:
    history: list[dict[str, object]] = []
    placeholder = WaitingPlaceholder()
    while True:
        try:
            query = input("\033[36mmini_code >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        if query.strip() == "/resume":
            if history:
                print("[resume unavailable: exit and reopen chat to restore a different session]")
                continue
            resumed = _resume_chat_session(app)
            if resumed is None:
                continue
            app, history = resumed
            continue
        if query.strip() == "/compact":
            if history:
                try:
                    history[:] = auto_compact(
                        history,
                        app.provider,
                        app.config,
                        progress=placeholder.update,
                    )
                finally:
                    placeholder.clear()
                _persist_session(app, history)
                print("[manual compact via /compact]")
            continue
        if query.strip() == "/tasks":
            print(app.task_manager.list_all())
            continue
        if query.strip() == "/team":
            print(app.teammate_manager.list_all())
            continue
        if query.strip() == "/inbox":
            print(json.dumps(app.message_bus.read_inbox("lead"), indent=2))
            continue
        history.append({"role": "user", "content": query})
        _persist_session(app, history)
        try:
            while True:
                keep_going = app.runtime.run_turn(history, progress=placeholder.update)
                placeholder.clear()
                _persist_session(app, history)
                reply = _extract_last_assistant_reply(history)
                if reply:
                    print(reply)
                for tool_call in _extract_last_tool_calls(history):
                    print(tool_call)
                if not keep_going:
                    break
        finally:
            placeholder.clear()
        print()
    return 0


def _extract_last_assistant_reply(history: list[dict[str, object]]) -> str:
    for message in reversed(history):
        if message.get("role") != "assistant":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return extract_text(content)
    return ""


def _extract_last_tool_calls(history: list[dict[str, object]]) -> list[str]:
    for message in reversed(history):
        if message.get("role") != "assistant":
            continue
        content = message.get("content")
        if not isinstance(content, list):
            return []
        return [_format_tool_call(block) for block in iter_tool_uses(content)]
    return []


def _format_tool_call(block: dict[str, object]) -> str:
    tool_name = str(block.get("name", "unknown"))
    tool_input = block.get("input")
    if not isinstance(tool_input, dict) or not tool_input:
        return f"[tool] {tool_name}"
    preview = json.dumps(tool_input, ensure_ascii=False, separators=(",", ":"))
    if len(preview) > TOOL_CALL_PREVIEW_LIMIT:
        preview = f"{preview[: TOOL_CALL_PREVIEW_LIMIT - 3]}..."
    return f"[tool] {tool_name} {preview}"


def _persist_session(app: AppContext, history: list[dict[str, object]]) -> None:
    app.session_manager.save(
        app.config.session_id,
        history,
        app.todo_manager.snapshot(),
    )


def _resume_chat_session(app: AppContext) -> tuple[AppContext, list[dict[str, object]]] | None:
    sessions = app.session_manager.list_all()
    if not sessions:
        print("[no resumable sessions]")
        return None
    print("Resumable sessions:")
    for index, session in enumerate(sessions, start=1):
        print(
            f"{index}. {session.updated_at} | {session.message_count} messages | "
            f"{session.preview}"
        )
    while True:
        choice = input("resume> ").strip()
        if not choice:
            print("[resume cancelled]")
            return None
        if not choice.isdigit():
            print("[enter a session number or press Enter to cancel]")
            continue
        selected_index = int(choice)
        if 1 <= selected_index <= len(sessions):
            break
        print("[invalid session number]")
    snapshot = app.session_manager.load(sessions[selected_index - 1].session_id)
    resumed_app = build_app(app.config.workdir, session_id=snapshot.session_id)
    resumed_app.todo_manager.restore([item.to_dict() for item in snapshot.todo_items])
    restored_history = list(snapshot.history)
    print(
        f"[resumed session {snapshot.session_id} | {snapshot.updated_at} | "
        f"{snapshot.message_count} messages]"
    )
    return resumed_app, restored_history


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    app = build_app(args.workdir)

    if args.command == "chat":
        return run_chat(app)

    if args.command == "tasks":
        if args.tasks_command == "list":
            print(app.task_manager.list_all())
        elif args.tasks_command == "get":
            print(app.task_manager.get(args.task_id))
        elif args.tasks_command == "create":
            print(app.task_manager.create(args.subject, args.description))
        elif args.tasks_command == "update":
            print(
                app.task_manager.update(
                    args.task_id,
                    status=args.status,
                    add_blocked_by=args.add_blocked_by,
                    add_blocks=args.add_blocks,
                )
            )
        return 0

    if args.command == "team":
        if args.team_command == "list":
            print(app.teammate_manager.list_all())
        elif args.team_command == "spawn":
            print(app.teammate_manager.spawn(args.name, args.role, args.prompt))
        elif args.team_command == "send":
            print(app.message_bus.send("lead", args.to, args.content, args.msg_type))
        elif args.team_command == "inbox":
            print(json.dumps(app.message_bus.read_inbox("lead"), indent=2))
        return 0

    if args.command == "bg":
        if args.bg_command == "list":
            print(app.background_manager.check())
        elif args.bg_command == "get":
            print(app.background_manager.check(args.task_id))
        return 0

    parser.error("Unknown command")
    return 2
