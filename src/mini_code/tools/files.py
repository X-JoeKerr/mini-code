from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ..config import AppConfig

PERSISTED_OPEN = "<persisted-output>"
PERSISTED_CLOSE = "</persisted-output>"


def safe_path(workdir: Path, candidate: str) -> Path:
    path = (workdir / candidate).resolve()
    if not path.is_relative_to(workdir.resolve()):
        raise ValueError(f"Path escapes workspace: {candidate}")
    return path


def _persist_tool_result(config: AppConfig, tool_use_id: str, content: str) -> Path:
    config.paths.tool_results_dir.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^a-zA-Z0-9_.-]", "_", tool_use_id or "unknown")
    path = config.paths.tool_results_dir / f"{safe_id}.txt"
    if not path.exists():
        path.write_text(content)
    return path.relative_to(config.workdir)


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size / (1024 * 1024):.1f}MB"


def _preview_slice(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    idx = text[:limit].rfind("\n")
    cut = idx if idx > (limit * 0.5) else limit
    return text[:cut], True


def _build_persisted_marker(config: AppConfig, stored_path: Path, content: str) -> str:
    preview, has_more = _preview_slice(content, config.persisted_preview_chars)
    marker = (
        f"{PERSISTED_OPEN}\n"
        f"Output too large ({_format_size(len(content))}). "
        f"Full output saved to: {stored_path}\n\n"
        f"Preview (first {_format_size(config.persisted_preview_chars)}):\n"
        f"{preview}"
    )
    if has_more:
        marker += "\n..."
    marker += f"\n{PERSISTED_CLOSE}"
    return marker


def maybe_persist_output(
    config: AppConfig,
    tool_use_id: str,
    output: str,
    trigger_chars: int | None = None,
) -> str:
    if not isinstance(output, str):
        return str(output)
    trigger = (
        config.persist_output_trigger_default
        if trigger_chars is None
        else int(trigger_chars)
    )
    if len(output) <= trigger:
        return output
    stored_path = _persist_tool_result(config, tool_use_id, output)
    return _build_persisted_marker(config, stored_path, output)


def run_bash(config: AppConfig, command: str, tool_use_id: str = "") -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(token in command for token in dangerous):
        return "Error: Dangerous command blocked"
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=config.workdir,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    output = (result.stdout + result.stderr).strip()
    if not output:
        return "(no output)"
    output = maybe_persist_output(
        config,
        tool_use_id,
        output,
        trigger_chars=config.persist_output_trigger_bash,
    )
    return output[: config.context_truncate_chars]


def run_read(
    config: AppConfig,
    path: str,
    tool_use_id: str = "",
    limit: int | None = None,
) -> str:
    try:
        lines = safe_path(config.workdir, path).read_text().splitlines()
        if limit is not None and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more)"]
        output = "\n".join(lines)
        output = maybe_persist_output(config, tool_use_id, output)
        return output[: config.context_truncate_chars]
    except Exception as exc:  # pragma: no cover - exercised via tests
        return f"Error: {exc}"


def run_write(config: AppConfig, path: str, content: str) -> str:
    try:
        target = safe_path(config.workdir, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as exc:  # pragma: no cover - exercised via tests
        return f"Error: {exc}"


def run_edit(config: AppConfig, path: str, old_text: str, new_text: str) -> str:
    try:
        target = safe_path(config.workdir, path)
        content = target.read_text()
        if old_text not in content:
            return f"Error: Text not found in {path}"
        target.write_text(content.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as exc:  # pragma: no cover - exercised via tests
        return f"Error: {exc}"
