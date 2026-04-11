from __future__ import annotations

from pathlib import Path


def build_system_prompt(skill_descriptions: str, workdir: Path) -> str:
    return (
        f"You are a coding agent at {workdir}. Use tools to solve tasks.\n"
        "Prefer task_create/task_update/task_list for multi-step work. "
        "Use TodoWrite for short checklists.\n"
        "Use task for subagent delegation. Use load_skill for specialized knowledge.\n"
        f"Skills: {skill_descriptions}"
    )
