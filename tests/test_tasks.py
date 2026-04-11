from __future__ import annotations

import json

from mini_code.config import WorkspacePaths
from mini_code.features.tasks import TaskManager


def make_manager(tmp_path):
    return TaskManager(WorkspacePaths(tmp_path))


def test_create_get_update_claim_and_list(tmp_path):
    manager = make_manager(tmp_path)
    created = json.loads(manager.create("Task A", "desc"))
    assert created["subject"] == "Task A"
    assert json.loads(manager.get(created["id"]))["description"] == "desc"
    manager.claim(created["id"], "lead")
    listed = manager.list_all()
    assert "@lead" in listed
    updated = json.loads(manager.update(created["id"], status="completed"))
    assert updated["status"] == "completed"


def test_completed_task_unblocks_dependents(tmp_path):
    manager = make_manager(tmp_path)
    first = json.loads(manager.create("Task A"))
    second = json.loads(manager.create("Task B"))
    manager.update(second["id"], add_blocked_by=[first["id"]])
    manager.update(first["id"], status="completed")
    updated_second = json.loads(manager.get(second["id"]))
    assert updated_second["blocked_by"] == []


def test_delete_task(tmp_path):
    manager = make_manager(tmp_path)
    created = json.loads(manager.create("Task A"))
    result = manager.update(created["id"], status="deleted")
    assert result == f"Task {created['id']} deleted"
