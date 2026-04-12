from __future__ import annotations

from mini_code.features.sessions import SessionManager


def test_session_manager_save_and_load_round_trip(tmp_path):
    manager = SessionManager(tmp_path / ".sessions")
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
    ]
    todo_items = [{"content": "write tests", "status": "in_progress", "active_form": "writing tests"}]

    manager.save("session-1", history, todo_items)
    snapshot = manager.load("session-1")

    assert snapshot.session_id == "session-1"
    assert snapshot.history == history
    assert snapshot.todo_items[0].content == "write tests"
    assert snapshot.preview == "hello"
    assert snapshot.message_count == 2


def test_session_manager_lists_most_recent_first(tmp_path):
    manager = SessionManager(tmp_path / ".sessions")

    manager.save("older", [{"role": "user", "content": "older"}], [])
    manager.save("newer", [{"role": "user", "content": "newer"}], [])

    sessions = manager.list_all()

    assert [item.session_id for item in sessions] == ["newer", "older"]


def test_session_manager_ignores_invalid_files_in_listing(tmp_path):
    manager = SessionManager(tmp_path / ".sessions")
    manager.save("valid", [{"role": "user", "content": "hi"}], [])
    (tmp_path / ".sessions" / "session_broken.json").write_text("{not json", encoding="utf-8")

    sessions = manager.list_all()

    assert [item.session_id for item in sessions] == ["valid"]
