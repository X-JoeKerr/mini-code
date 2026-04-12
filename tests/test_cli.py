from __future__ import annotations

from dataclasses import dataclass

from mini_code import cli
from mini_code.features.sessions import SessionSnapshot, SessionSummary
from mini_code.models import TodoItem


@dataclass
class DummyManager:
    result: str

    def list_all(self):
        return self.result

    def get(self, task_id):
        return f"get {task_id}"

    def create(self, subject, description=""):
        return f"create {subject} {description}"

    def update(self, task_id, status=None, add_blocked_by=None, add_blocks=None):
        return f"update {task_id} {status}"

    def check(self, task_id=None):
        return self.result if task_id is None else f"check {task_id}"

    def spawn(self, name, role, prompt):
        return f"spawn {name} {role} {prompt}"


@dataclass
class DummyBus:
    def send(self, sender, to, content, msg_type="message"):
        return f"send {sender} {to} {msg_type} {content}"

    def read_inbox(self, name):
        return [{"from": "bob", "content": "hello"}]


@dataclass
class DummySessionManager:
    summaries: list[SessionSummary] | None = None
    snapshots: dict[str, SessionSnapshot] | None = None
    saves: list[tuple[str, list[dict], list[dict[str, str]]]] | None = None

    def save(self, session_id, history, todo_items):
        if self.saves is None:
            self.saves = []
        self.saves.append((session_id, list(history), list(todo_items)))

    def list_all(self):
        return list(self.summaries or [])

    def load(self, session_id):
        snapshots = self.snapshots or {}
        return snapshots[session_id]


@dataclass
class DummyApp:
    config: object
    provider: object
    todo_manager: object
    session_manager: DummySessionManager
    task_manager: DummyManager
    teammate_manager: DummyManager
    background_manager: DummyManager
    message_bus: DummyBus


@dataclass
class DummyRuntime:
    reply: str = "assistant reply"
    replies: list[str] | None = None
    contents: list[list[dict]] | None = None

    def run_turn(self, history, progress=None):
        if self.contents is not None:
            if not self.contents:
                return False
            history.append({"role": "assistant", "content": self.contents.pop(0)})
            return bool(self.contents)
        replies = self.replies if self.replies is not None else [self.reply]
        if not replies:
            return False
        history.append({"role": "assistant", "content": [{"type": "text", "text": replies.pop(0)}]})
        return bool(replies)


def test_tasks_list(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "build_app",
        lambda workdir=None, session_id=None: DummyApp(
            object(),
            object(),
            object(),
            DummySessionManager(),
            DummyManager("task list"),
            DummyManager("team"),
            DummyManager("bg"),
            DummyBus(),
        ),
    )
    assert cli.main(["tasks", "list"]) == 0
    assert "task list" in capsys.readouterr().out


def test_team_list(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "build_app",
        lambda workdir=None, session_id=None: DummyApp(
            object(),
            object(),
            object(),
            DummySessionManager(),
            DummyManager("task"),
            DummyManager("team list"),
            DummyManager("bg"),
            DummyBus(),
        ),
    )
    assert cli.main(["team", "list"]) == 0
    assert "team list" in capsys.readouterr().out


def test_bg_list(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "build_app",
        lambda workdir=None, session_id=None: DummyApp(
            object(),
            object(),
            object(),
            DummySessionManager(),
            DummyManager("task"),
            DummyManager("team"),
            DummyManager("bg list"),
            DummyBus(),
        ),
    )
    assert cli.main(["bg", "list"]) == 0
    assert "bg list" in capsys.readouterr().out


def test_parser_accepts_workdir():
    parser = cli.build_parser()
    args = parser.parse_args(["--workdir", "/tmp/demo", "tasks", "list"])
    assert str(args.workdir) == "/tmp/demo"


def test_chat_prints_last_assistant_reply(monkeypatch, capsys):
    app = type(
        "ChatApp",
        (),
        {
            "task_manager": DummyManager("task"),
            "teammate_manager": DummyManager("team"),
            "background_manager": DummyManager("bg"),
            "message_bus": DummyBus(),
            "runtime": DummyRuntime("hello from model"),
            "provider": object(),
            "config": type("Config", (), {"session_id": "session-1", "workdir": "/tmp/demo"})(),
            "todo_manager": type("Todo", (), {"snapshot": lambda self: []})(),
            "session_manager": DummySessionManager(),
        },
    )()
    responses = iter(["hi", "exit"])
    monkeypatch.setattr(cli, "build_app", lambda workdir=None, session_id=None: app)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(responses))

    assert cli.main(["chat"]) == 0
    assert "hello from model" in capsys.readouterr().out


def test_chat_prints_assistant_messages_from_tool_turns(monkeypatch, capsys):
    app = type(
        "ChatApp",
        (),
        {
            "task_manager": DummyManager("task"),
            "teammate_manager": DummyManager("team"),
            "background_manager": DummyManager("bg"),
            "message_bus": DummyBus(),
            "runtime": DummyRuntime(replies=["先看一下文件", "已经处理好了"]),
            "provider": object(),
            "config": type("Config", (), {"session_id": "session-2", "workdir": "/tmp/demo"})(),
            "todo_manager": type("Todo", (), {"snapshot": lambda self: []})(),
            "session_manager": DummySessionManager(),
        },
    )()
    responses = iter(["hi", "exit"])
    monkeypatch.setattr(cli, "build_app", lambda workdir=None, session_id=None: app)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(responses))

    assert cli.main(["chat"]) == 0
    output = capsys.readouterr().out
    assert "先看一下文件" in output
    assert "已经处理好了" in output


def test_chat_prints_tool_calls(monkeypatch, capsys):
    app = type(
        "ChatApp",
        (),
        {
            "task_manager": DummyManager("task"),
            "teammate_manager": DummyManager("team"),
            "background_manager": DummyManager("bg"),
            "message_bus": DummyBus(),
            "runtime": DummyRuntime(
                contents=[
                    [
                        {"type": "text", "text": "我先读取配置"},
                        {"type": "tool_use", "id": "1", "name": "read_file", "input": {"path": "pyproject.toml"}},
                    ],
                    [{"type": "text", "text": "看完了"}],
                ]
            ),
            "provider": object(),
            "config": type("Config", (), {"session_id": "session-3", "workdir": "/tmp/demo"})(),
            "todo_manager": type("Todo", (), {"snapshot": lambda self: []})(),
            "session_manager": DummySessionManager(),
        },
    )()
    responses = iter(["hi", "exit"])
    monkeypatch.setattr(cli, "build_app", lambda workdir=None, session_id=None: app)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(responses))

    assert cli.main(["chat"]) == 0
    output = capsys.readouterr().out
    assert "我先读取配置" in output
    assert '[tool] read_file {"path":"pyproject.toml"}' in output
    assert "看完了" in output


def test_chat_truncates_long_tool_call_preview(monkeypatch, capsys):
    app = type(
        "ChatApp",
        (),
        {
            "task_manager": DummyManager("task"),
            "teammate_manager": DummyManager("team"),
            "background_manager": DummyManager("bg"),
            "message_bus": DummyBus(),
            "runtime": DummyRuntime(
                contents=[
                    [
                        {"type": "text", "text": "我先执行命令"},
                        {
                            "type": "tool_use",
                            "id": "1",
                            "name": "bash",
                            "input": {"command": "x" * 200},
                        },
                    ],
                    [{"type": "text", "text": "执行完成"}],
                ]
            ),
            "provider": object(),
            "config": type("Config", (), {"session_id": "session-4", "workdir": "/tmp/demo"})(),
            "todo_manager": type("Todo", (), {"snapshot": lambda self: []})(),
            "session_manager": DummySessionManager(),
        },
    )()
    responses = iter(["hi", "exit"])
    monkeypatch.setattr(cli, "build_app", lambda workdir=None, session_id=None: app)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(responses))

    assert cli.main(["chat"]) == 0
    output = capsys.readouterr().out
    assert "[tool] bash " in output
    assert '"command":"' in output
    assert "..." in output


def test_chat_resume_restores_history_and_todos(monkeypatch, capsys):
    restored_todo_manager = type(
        "TodoManager",
        (),
        {
            "__init__": lambda self: setattr(self, "restored", []),
            "snapshot": lambda self: [],
            "restore": lambda self, items: setattr(self, "restored", items),
        },
    )()
    restored_app = type(
        "ChatApp",
        (),
        {
            "task_manager": DummyManager("task"),
            "teammate_manager": DummyManager("team"),
            "background_manager": DummyManager("bg"),
            "message_bus": DummyBus(),
            "runtime": DummyRuntime(reply="继续完成"),
            "provider": object(),
            "config": type("Config", (), {"session_id": "resume-1", "workdir": "/tmp/demo"})(),
            "todo_manager": restored_todo_manager,
            "session_manager": DummySessionManager(),
        },
    )()
    initial_app = type(
        "ChatApp",
        (),
        {
            "task_manager": DummyManager("task"),
            "teammate_manager": DummyManager("team"),
            "background_manager": DummyManager("bg"),
            "message_bus": DummyBus(),
            "runtime": DummyRuntime(reply="should not be used"),
            "provider": object(),
            "config": type("Config", (), {"session_id": "fresh-1", "workdir": "/tmp/demo"})(),
            "todo_manager": type("Todo", (), {"snapshot": lambda self: [], "restore": lambda self, items: None})(),
            "session_manager": DummySessionManager(
                summaries=[
                    SessionSummary(
                        session_id="resume-1",
                        created_at="2026-04-12T00:00:00+00:00",
                        updated_at="2026-04-12T01:00:00+00:00",
                        preview="之前的话题",
                        message_count=3,
                    )
                ],
                snapshots={
                    "resume-1": SessionSnapshot(
                        session_id="resume-1",
                        created_at="2026-04-12T00:00:00+00:00",
                        updated_at="2026-04-12T01:00:00+00:00",
                        history=[{"role": "user", "content": "之前的话题"}],
                        todo_items=[TodoItem(content="继续处理", status="in_progress", active_form="continuing")],
                        preview="之前的话题",
                        message_count=3,
                    )
                },
            ),
        },
    )()
    responses = iter(["/resume", "1", "继续", "exit"])
    monkeypatch.setattr(
        cli,
        "build_app",
        lambda workdir=None, session_id=None: restored_app if session_id == "resume-1" else initial_app,
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": next(responses))

    assert cli.main(["chat"]) == 0
    output = capsys.readouterr().out
    assert "[resumed session resume-1" in output
    assert "继续完成" in output
    assert restored_todo_manager.restored == [
        {"content": "继续处理", "status": "in_progress", "active_form": "continuing"}
    ]


def test_chat_resume_rejects_non_empty_history(monkeypatch, capsys):
    app = type(
        "ChatApp",
        (),
        {
            "task_manager": DummyManager("task"),
            "teammate_manager": DummyManager("team"),
            "background_manager": DummyManager("bg"),
            "message_bus": DummyBus(),
            "runtime": DummyRuntime(reply="hello"),
            "provider": object(),
            "config": type("Config", (), {"session_id": "fresh-1", "workdir": "/tmp/demo"})(),
            "todo_manager": type("Todo", (), {"snapshot": lambda self: [], "restore": lambda self, items: None})(),
            "session_manager": DummySessionManager(),
        },
    )()
    responses = iter(["hi", "/resume", "exit"])
    monkeypatch.setattr(cli, "build_app", lambda workdir=None, session_id=None: app)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(responses))

    assert cli.main(["chat"]) == 0
    output = capsys.readouterr().out
    assert "[resume unavailable: exit and reopen chat to restore a different session]" in output


def test_chat_resume_handles_empty_and_cancel(monkeypatch, capsys):
    no_session_app = type(
        "ChatApp",
        (),
        {
            "task_manager": DummyManager("task"),
            "teammate_manager": DummyManager("team"),
            "background_manager": DummyManager("bg"),
            "message_bus": DummyBus(),
            "runtime": DummyRuntime(reply="unused"),
            "provider": object(),
            "config": type("Config", (), {"session_id": "fresh-1", "workdir": "/tmp/demo"})(),
            "todo_manager": type("Todo", (), {"snapshot": lambda self: [], "restore": lambda self, items: None})(),
            "session_manager": DummySessionManager(),
        },
    )()
    responses = iter(["/resume", "exit"])
    monkeypatch.setattr(cli, "build_app", lambda workdir=None, session_id=None: no_session_app)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(responses))
    assert cli.main(["chat"]) == 0
    assert "[no resumable sessions]" in capsys.readouterr().out

    cancel_app = type(
        "ChatApp",
        (),
        {
            "task_manager": DummyManager("task"),
            "teammate_manager": DummyManager("team"),
            "background_manager": DummyManager("bg"),
            "message_bus": DummyBus(),
            "runtime": DummyRuntime(reply="unused"),
            "provider": object(),
            "config": type("Config", (), {"session_id": "fresh-2", "workdir": "/tmp/demo"})(),
            "todo_manager": type("Todo", (), {"snapshot": lambda self: [], "restore": lambda self, items: None})(),
            "session_manager": DummySessionManager(
                summaries=[
                    SessionSummary(
                        session_id="resume-2",
                        created_at="2026-04-12T00:00:00+00:00",
                        updated_at="2026-04-12T01:00:00+00:00",
                        preview="another chat",
                        message_count=2,
                    )
                ],
                snapshots={},
            ),
        },
    )()
    responses = iter(["/resume", "", "exit"])
    monkeypatch.setattr(cli, "build_app", lambda workdir=None, session_id=None: cancel_app)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(responses))
    assert cli.main(["chat"]) == 0
    assert "[resume cancelled]" in capsys.readouterr().out
