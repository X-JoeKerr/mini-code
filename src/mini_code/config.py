from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback for bare environments
    def load_dotenv(*args, **kwargs):  # type: ignore[no-redef]
        return False


@dataclass(slots=True)
class WorkspacePaths:
    workdir: Path
    team_dir: Path = field(init=False)
    inbox_dir: Path = field(init=False)
    tasks_dir: Path = field(init=False)
    skills_dir: Path = field(init=False)
    transcripts_dir: Path = field(init=False)
    task_outputs_dir: Path = field(init=False)
    tool_results_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.workdir = self.workdir.resolve()
        self.team_dir = self.workdir / ".team"
        self.inbox_dir = self.team_dir / "inbox"
        self.tasks_dir = self.workdir / ".tasks"
        self.skills_dir = self.workdir / "skills"
        self.transcripts_dir = self.workdir / ".transcripts"
        self.task_outputs_dir = self.workdir / ".task_outputs"
        self.tool_results_dir = self.task_outputs_dir / "tool-results"

    def ensure_directories(self) -> None:
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        self.tool_results_dir.mkdir(parents=True, exist_ok=True)


@dataclass(slots=True)
class AppConfig:
    workdir: Path
    model_id: str
    anthropic_base_url: str | None = None
    token_threshold: int = 100000
    poll_interval: int = 5
    idle_timeout: int = 60
    context_truncate_chars: int = 50000
    persist_output_trigger_default: int = 50000
    persist_output_trigger_bash: int = 30000
    persisted_preview_chars: int = 2000
    keep_recent_tool_results: int = 3
    max_tool_output_chars: int = 50000
    paths: WorkspacePaths = field(init=False)

    def __post_init__(self) -> None:
        self.workdir = self.workdir.resolve()
        self.paths = WorkspacePaths(self.workdir)

    @classmethod
    def from_env(cls, workdir: Path | None = None) -> "AppConfig":
        load_dotenv(override=True)
        resolved_workdir = (workdir or Path.cwd()).resolve()
        anthropic_base_url = os.getenv("ANTHROPIC_BASE_URL")
        if anthropic_base_url:
            os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
        model_id = os.getenv("MODEL_ID")
        if not model_id:
            raise ValueError("MODEL_ID environment variable is required")
        config = cls(
            workdir=resolved_workdir,
            model_id=model_id,
            anthropic_base_url=anthropic_base_url,
        )
        config.paths.ensure_directories()
        return config
