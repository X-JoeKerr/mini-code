from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

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
    sessions_dir: Path = field(init=False)
    skills_dir: Path = field(init=False)
    logs_dir: Path = field(init=False)
    llm_logs_dir: Path = field(init=False)
    transcripts_dir: Path = field(init=False)
    task_outputs_dir: Path = field(init=False)
    tool_results_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.workdir = self.workdir.resolve()
        self.team_dir = self.workdir / ".team"
        self.inbox_dir = self.team_dir / "inbox"
        self.tasks_dir = self.workdir / ".tasks"
        self.sessions_dir = self.workdir / ".sessions"
        self.skills_dir = self.workdir / "skills"
        self.logs_dir = self.workdir / ".logs"
        self.llm_logs_dir = self.logs_dir / "llm"
        self.transcripts_dir = self.workdir / ".transcripts"
        self.task_outputs_dir = self.workdir / ".task_outputs"
        self.tool_results_dir = self.task_outputs_dir / "tool-results"

    def ensure_directories(self) -> None:
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.llm_logs_dir.mkdir(parents=True, exist_ok=True)
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        self.tool_results_dir.mkdir(parents=True, exist_ok=True)


def generate_session_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid4().hex[:8]}"


DEFAULT_ENV_FILE_NAME = ".env"
ENV_FILE_OVERRIDE_VAR = "MINI_CODE_ENV_FILE"


def resolve_env_file(workdir: Path) -> Path:
    override = os.getenv(ENV_FILE_OVERRIDE_VAR)
    if override:
        return Path(override).expanduser().resolve()
    return workdir / DEFAULT_ENV_FILE_NAME


@dataclass(slots=True)
class AppConfig:
    workdir: Path
    model_id: str
    anthropic_base_url: str | None = None
    session_id: str = field(default_factory=generate_session_id)
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
    llm_session_log_path: Path = field(init=False)
    env_file_path: Path = field(init=False)

    def __post_init__(self) -> None:
        self.workdir = self.workdir.resolve()
        self.paths = WorkspacePaths(self.workdir)
        self.llm_session_log_path = self.paths.llm_logs_dir / f"session_{self.session_id}.jsonl"
        self.env_file_path = resolve_env_file(self.workdir)

    @classmethod
    def from_env(
        cls,
        workdir: Path | None = None,
        session_id: str | None = None,
    ) -> "AppConfig":
        resolved_workdir = (workdir or Path.cwd()).resolve()
        load_dotenv(dotenv_path=resolve_env_file(resolved_workdir), override=True)
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
            session_id=session_id or generate_session_id(),
        )
        config.paths.ensure_directories()
        return config
