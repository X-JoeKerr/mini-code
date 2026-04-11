from __future__ import annotations

from mini_code.config import AppConfig
from mini_code.tools.files import (
    maybe_persist_output,
    run_edit,
    run_read,
    run_write,
    safe_path,
)


def make_config(tmp_path):
    config = AppConfig(workdir=tmp_path, model_id="test-model")
    config.paths.ensure_directories()
    return config


def test_safe_path_blocks_escape(tmp_path):
    try:
        safe_path(tmp_path, "../oops.txt")
    except ValueError as exc:
        assert "Path escapes workspace" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError")


def test_run_read_respects_limit(tmp_path):
    config = make_config(tmp_path)
    (tmp_path / "demo.txt").write_text("a\nb\nc\n")
    output = run_read(config, "demo.txt", limit=2)
    assert output == "a\nb\n... (1 more)"


def test_run_write_creates_parent_dirs(tmp_path):
    config = make_config(tmp_path)
    result = run_write(config, "nested/demo.txt", "hello")
    assert "Wrote 5 bytes" in result
    assert (tmp_path / "nested" / "demo.txt").read_text() == "hello"


def test_run_edit_reports_missing_text(tmp_path):
    config = make_config(tmp_path)
    (tmp_path / "demo.txt").write_text("hello")
    result = run_edit(config, "demo.txt", "bye", "ciao")
    assert "Text not found" in result


def test_large_output_is_persisted(tmp_path):
    config = make_config(tmp_path)
    config.persist_output_trigger_default = 10
    output = maybe_persist_output(config, "tool-1", "x" * 20)
    assert "<persisted-output>" in output
    assert (config.paths.tool_results_dir / "tool-1.txt").exists()
