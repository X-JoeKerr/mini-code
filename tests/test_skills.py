from __future__ import annotations

from mini_code.features.skills import SkillLoader


def test_skill_loader_discovers_skills(tmp_path):
    skill_dir = tmp_path / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: test skill\n---\nSkill body"
    )
    loader = SkillLoader(tmp_path / "skills")
    assert "demo" in loader.descriptions()
    assert "Skill body" in loader.load("demo")


def test_skill_loader_unknown_skill(tmp_path):
    loader = SkillLoader(tmp_path / "skills")
    assert "Unknown skill" in loader.load("missing")
