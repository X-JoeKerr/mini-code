from __future__ import annotations

import time

from mini_code.config import AppConfig
from mini_code.features.background import BackgroundManager


def make_manager(tmp_path):
    config = AppConfig(workdir=tmp_path, model_id="test-model")
    return BackgroundManager(config)


def wait_for(predicate, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_background_task_completes(tmp_path):
    manager = make_manager(tmp_path)
    message = manager.run("printf 'hello'")
    task_id = message.split()[2]
    assert wait_for(lambda: manager.tasks[task_id].status != "running")
    assert manager.tasks[task_id].result == "hello"


def test_background_task_failure(tmp_path):
    manager = make_manager(tmp_path)
    message = manager.run("command_that_should_not_exist_xyz")
    task_id = message.split()[2]
    assert wait_for(lambda: manager.tasks[task_id].status != "running")
    assert manager.tasks[task_id].status == "completed"


def test_drain_notifications(tmp_path):
    manager = make_manager(tmp_path)
    task_id = manager.run("printf 'hello'").split()[2]
    assert wait_for(lambda: manager.tasks[task_id].status != "running")
    notifications = manager.drain()
    assert notifications
    assert manager.drain() == []
