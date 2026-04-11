from __future__ import annotations

from dataclasses import dataclass

from mini_code.config import AppConfig
from mini_code.features.background import BackgroundManager
from mini_code.features.skills import SkillLoader
from mini_code.features.tasks import TaskManager
from mini_code.features.team import MessageBus, TeammateManager
from mini_code.features.todo import TodoManager
from mini_code.runtime import AgentRuntime, auto_compact, microcompact


@dataclass
class FakeResponse:
    content: list[dict]
    stop_reason: str


class QueueProvider:
    def __init__(self, responses):
        self.responses = list(responses)

    def create_message(self, system, messages, tools, max_tokens):
        return self.responses.pop(0)


def make_runtime(tmp_path, responses):
    config = AppConfig(workdir=tmp_path, model_id="test-model")
    config.paths.ensure_directories()
    provider = QueueProvider(responses)
    todo = TodoManager()
    skills = SkillLoader(config.paths.skills_dir)
    tasks = TaskManager(config.paths)
    bg = BackgroundManager(config)
    bus = MessageBus(config.paths.inbox_dir)
    team = TeammateManager(config, provider, tasks, bus)
    runtime = AgentRuntime(config, provider, todo, skills, tasks, bg, bus, team)
    return config, provider, todo, tasks, bg, bus, runtime


def test_microcompact_replaces_old_tool_results():
    messages = [
        {"role": "assistant", "content": [{"type": "tool_use", "id": "1", "name": "bash"}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "1", "content": "x" * 200}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "2", "content": "y" * 200}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "3", "content": "z" * 200}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "4", "content": "w" * 200}]},
    ]
    microcompact(messages, keep_recent=2)
    assert messages[1]["content"][0]["content"] == "[Previous: used bash]"


def test_auto_compact_writes_transcript(tmp_path):
    config = AppConfig(workdir=tmp_path, model_id="test-model")
    config.paths.ensure_directories()
    provider = QueueProvider([FakeResponse(content=[{"type": "text", "text": "summary"}], stop_reason="end_turn")])
    result = auto_compact([{"role": "user", "content": "hello"}], provider, config)
    assert "summary" in result[0]["content"]
    assert list(config.paths.transcripts_dir.glob("transcript_*.jsonl"))


def test_runtime_injects_background_and_inbox(tmp_path):
    responses = [FakeResponse(content=[{"type": "text", "text": "done"}], stop_reason="end_turn")]
    _, _, _, _, bg, bus, runtime = make_runtime(tmp_path, responses)
    bg.notifications.put({"task_id": "abc", "status": "completed", "result": "ok"})
    bus.send("bob", "lead", "hi")
    history = [{"role": "user", "content": "hello"}]
    assert runtime.run_turn(history) is False
    assert any("background-results" in str(item["content"]) for item in history)
    assert any("<inbox>" in str(item["content"]) for item in history)


def test_runtime_manual_compress(tmp_path):
    responses = [
        FakeResponse(
            content=[{"type": "tool_use", "id": "1", "name": "compress", "input": {"focus": "tasks"}}],
            stop_reason="tool_use",
        ),
        FakeResponse(content=[{"type": "text", "text": "summary"}], stop_reason="end_turn"),
    ]
    _, _, _, _, _, _, runtime = make_runtime(tmp_path, responses)
    history = [{"role": "user", "content": "hello"}]
    assert runtime.run_turn(history) is True
    assert "summary" in history[0]["content"]


def test_todo_reminder_after_three_rounds(tmp_path):
    responses = [
        FakeResponse(content=[{"type": "tool_use", "id": "1", "name": "task_list", "input": {}}], stop_reason="tool_use"),
        FakeResponse(content=[{"type": "tool_use", "id": "2", "name": "task_list", "input": {}}], stop_reason="tool_use"),
        FakeResponse(content=[{"type": "tool_use", "id": "3", "name": "task_list", "input": {}}], stop_reason="tool_use"),
    ]
    _, _, todo, _, _, _, runtime = make_runtime(tmp_path, responses)
    todo.update([{"content": "a", "status": "in_progress", "active_form": "doing a"}])
    history = [{"role": "user", "content": "hello"}]
    runtime.run_turn(history)
    runtime.run_turn(history)
    runtime.run_turn(history)
    last_user = history[-1]["content"]
    assert last_user[0]["text"] == "<reminder>Update your todos.</reminder>"
