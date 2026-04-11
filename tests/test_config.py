from __future__ import annotations

from pathlib import Path

import pytest

from mini_code.config import AppConfig, WorkspacePaths


def test_from_env_requires_model_id(monkeypatch, tmp_path):
    monkeypatch.delenv("MODEL_ID", raising=False)
    with pytest.raises(ValueError, match="MODEL_ID"):
        AppConfig.from_env(tmp_path)


def test_workspace_paths_are_computed(tmp_path):
    paths = WorkspacePaths(tmp_path)
    assert paths.team_dir == tmp_path / ".team"
    assert paths.inbox_dir == tmp_path / ".team" / "inbox"
    assert paths.tool_results_dir == tmp_path / ".task_outputs" / "tool-results"


def test_from_env_allows_anthropic_base_url(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_ID", "test-model")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "remove-me")
    config = AppConfig.from_env(tmp_path)
    assert config.anthropic_base_url == "https://example.com"
    assert "ANTHROPIC_AUTH_TOKEN" not in __import__("os").environ
