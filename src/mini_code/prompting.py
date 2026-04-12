from __future__ import annotations

from pathlib import Path


def build_system_prompt(skill_descriptions: str, workdir: Path) -> str:
    return (
        f"You are a coding agent at {workdir}. Use tools to solve tasks.\n"
        f"Treat {workdir} as your workspace boundary. Create new files, directories, branches, and git "
        "worktrees inside this directory unless the user explicitly asks for a different location.\n"
        f"When creating git worktrees, prefer paths under {workdir / '.worktrees'} and double-check "
        "relative paths so they do not escape the workspace.\n"
        "Prefer task_create/task_update/task_list for multi-step work. "
        "Use TodoWrite for short checklists.\n"
        "Use task for subagent delegation. Use load_skill for specialized knowledge.\n"
        f"Skills: {skill_descriptions}"
    )
