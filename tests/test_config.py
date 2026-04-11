from __future__ import annotations

from pathlib import Path

import pytest

from mini_code.config import AppConfig, WorkspacePaths, resolve_env_file


def test_from_env_requires_model_id(monkeypatch, tmp_path):
    monkeypatch.delenv("MODEL_ID", raising=False)
    with pytest.raises(ValueError, match="MODEL_ID"):
        AppConfig.from_env(tmp_path)


def test_workspace_paths_are_computed(tmp_path):
    paths = WorkspacePaths(tmp_path)
    assert paths.team_dir == tmp_path / ".team"
    assert paths.inbox_dir == tmp_path / ".team" / "inbox"
    assert paths.llm_logs_dir == tmp_path / ".logs" / "llm"
    assert paths.tool_results_dir == tmp_path / ".task_outputs" / "tool-results"


def test_from_env_allows_anthropic_base_url(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_ID", "test-model")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "remove-me")
    config = AppConfig.from_env(tmp_path)
    assert config.anthropic_base_url == "https://example.com"
    assert "ANTHROPIC_AUTH_TOKEN" not in __import__("os").environ


def test_app_config_exposes_session_log_path(tmp_path):
    config = AppConfig(workdir=tmp_path, model_id="test-model", session_id="session-123")
    assert config.llm_session_log_path == tmp_path / ".logs" / "llm" / "session_session-123.jsonl"


def test_from_env_loads_default_workdir_dotenv(monkeypatch, tmp_path):
    monkeypatch.delenv("MODEL_ID", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    (tmp_path / ".env").write_text(
        "MODEL_ID=dotenv-model\nANTHROPIC_BASE_URL=https://dotenv.example.com\n",
        encoding="utf-8",
    )

    config = AppConfig.from_env(tmp_path)

    assert config.model_id == "dotenv-model"
    assert config.anthropic_base_url == "https://dotenv.example.com"
    assert config.env_file_path == tmp_path / ".env"


def test_resolve_env_file_prefers_override(monkeypatch, tmp_path):
    custom_env = tmp_path / "custom.env"
    monkeypatch.setenv("MINI_CODE_ENV_FILE", str(custom_env))

    assert resolve_env_file(tmp_path) == custom_env


def test_from_env_uses_override_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("MODEL_ID", raising=False)
    custom_env = tmp_path / "custom.env"
    custom_env.write_text("MODEL_ID=override-model\n", encoding="utf-8")
    monkeypatch.setenv("MINI_CODE_ENV_FILE", str(custom_env))

    config = AppConfig.from_env(tmp_path)

    assert config.model_id == "override-model"
    assert config.env_file_path == custom_env
