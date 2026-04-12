from __future__ import annotations

from pathlib import Path

from mini_code.prompting import build_system_prompt


def test_system_prompt_keeps_new_artifacts_inside_workdir():
    workdir = Path("/tmp/test")

    prompt = build_system_prompt("worktree", workdir)

    assert "Treat /tmp/test as your workspace boundary." in prompt
    assert "unless the user explicitly asks for a different location" in prompt
    assert "When creating git worktrees, prefer paths under /tmp/test/.worktrees" in prompt
    assert "do not escape the workspace" in prompt
