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

    def agent_loop(self, history, progress=None):
        history.append({"role": "assistant", "content": [{"type": "text", "text": self.reply}]})


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
