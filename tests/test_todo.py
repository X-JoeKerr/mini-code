from __future__ import annotations

import pytest

from mini_code.features.todo import TodoManager


def test_todo_validation_rules():
    manager = TodoManager()
    with pytest.raises(ValueError, match="Only one in_progress"):
        manager.update(
            [
                {"content": "a", "status": "in_progress", "active_form": "doing a"},
                {"content": "b", "status": "in_progress", "active_form": "doing b"},
            ]
        )


def test_todo_render_output():
    manager = TodoManager()
    output = manager.update(
        [
            {"content": "a", "status": "pending", "active_form": "doing a"},
            {"content": "b", "status": "completed", "active_form": "doing b"},
        ]
    )
    assert "[ ] a" in output
    assert "[x] b" in output
    assert "(1/2 completed)" in output


def test_has_open_items():
    manager = TodoManager()
    manager.update([{"content": "a", "status": "completed", "active_form": "done"}])
    assert not manager.has_open_items()
