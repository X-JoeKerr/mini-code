from __future__ import annotations

import json

from mini_code.config import AppConfig
from mini_code.features.tasks import TaskManager
from mini_code.features.team import MessageBus, PlanApprovalRegistry, ShutdownRegistry, TeammateManager


class DummyProvider:
    def create_message(self, system, messages, tools, max_tokens):
        raise RuntimeError("not used in this test")


def make_team(tmp_path):
    config = AppConfig(workdir=tmp_path, model_id="test-model")
    config.paths.ensure_directories()
    bus = MessageBus(config.paths.inbox_dir)
    task_manager = TaskManager(config.paths)
    shutdown = ShutdownRegistry()
    plan = PlanApprovalRegistry()
    team = TeammateManager(config, DummyProvider(), task_manager, bus, shutdown, plan)
    return config, bus, shutdown, plan, team


def test_message_bus_send_and_read(tmp_path):
    _, bus, _, _, _ = make_team(tmp_path)
    bus.send("lead", "alice", "hello")
    messages = bus.read_inbox("alice")
    assert messages[0]["content"] == "hello"
    assert bus.read_inbox("alice") == []


def test_broadcast(tmp_path):
    _, bus, _, _, team = make_team(tmp_path)
    team.config_state["members"] = [{"name": "lead", "role": "lead", "status": "working"}, {"name": "bob", "role": "dev", "status": "idle"}]
    team._save()
    result = bus.broadcast("lead", "ping", team.member_names())
    assert "Broadcast to 1 teammates" == result


def test_shutdown_registry(tmp_path):
    _, bus, shutdown, _, _ = make_team(tmp_path)
    result = shutdown.request_shutdown("alice", bus)
    assert "Shutdown request" in result
    messages = bus.read_inbox("alice")
    assert messages[0]["type"] == "shutdown_request"


def test_plan_approval_registry(tmp_path):
    _, bus, _, plan, _ = make_team(tmp_path)
    request_id = plan.register_request("alice")
    result = plan.review(request_id, True, "looks good", bus)
    assert "approved" in result
    messages = bus.read_inbox("alice")
    assert messages[0]["type"] == "plan_approval_response"
