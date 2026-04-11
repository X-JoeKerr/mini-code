from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .config import AppConfig
from .features.background import BackgroundManager
from .features.skills import SkillLoader
from .features.tasks import TaskManager
from .features.team import MessageBus, PlanApprovalRegistry, ShutdownRegistry, TeammateManager
from .features.todo import TodoManager
from .llm import AnthropicProvider, extract_text
from .runtime import AgentRuntime, auto_compact


@dataclass
class AppContext:
    config: AppConfig
    provider: AnthropicProvider
    todo_manager: TodoManager
    skill_loader: SkillLoader
    task_manager: TaskManager
    background_manager: BackgroundManager
    message_bus: MessageBus
    teammate_manager: TeammateManager
    runtime: AgentRuntime


def build_app(workdir: Path | None = None) -> AppContext:
    config = AppConfig.from_env(workdir=workdir)
    provider = AnthropicProvider(config)
    todo_manager = TodoManager()
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
    while True:
        try:
            query = input("\033[36mmini_code >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        if query.strip() == "/compact":
            if history:
                history[:] = auto_compact(history, app.provider, app.config)
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
        app.runtime.agent_loop(history)
        reply = _extract_last_assistant_reply(history)
        if reply:
            print(reply)
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
