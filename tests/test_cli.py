from __future__ import annotations

from dataclasses import dataclass

from mini_code import cli


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
class DummyApp:
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
        lambda workdir=None: DummyApp(DummyManager("task list"), DummyManager("team"), DummyManager("bg"), DummyBus()),
    )
    assert cli.main(["tasks", "list"]) == 0
    assert "task list" in capsys.readouterr().out


def test_team_list(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "build_app",
        lambda workdir=None: DummyApp(DummyManager("task"), DummyManager("team list"), DummyManager("bg"), DummyBus()),
    )
    assert cli.main(["team", "list"]) == 0
    assert "team list" in capsys.readouterr().out


def test_bg_list(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "build_app",
        lambda workdir=None: DummyApp(DummyManager("task"), DummyManager("team"), DummyManager("bg list"), DummyBus()),
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
            "config": object(),
        },
    )()
    responses = iter(["hi", "exit"])
    monkeypatch.setattr(cli, "build_app", lambda workdir=None: app)
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
            "config": object(),
        },
    )()
    responses = iter(["hi", "exit"])
    monkeypatch.setattr(cli, "build_app", lambda workdir=None: app)
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
            "config": object(),
        },
    )()
    responses = iter(["hi", "exit"])
    monkeypatch.setattr(cli, "build_app", lambda workdir=None: app)
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
            "config": object(),
        },
    )()
    responses = iter(["hi", "exit"])
    monkeypatch.setattr(cli, "build_app", lambda workdir=None: app)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(responses))

    assert cli.main(["chat"]) == 0
    output = capsys.readouterr().out
    assert "[tool] bash " in output
    assert '"command":"' in output
    assert "..." in output
