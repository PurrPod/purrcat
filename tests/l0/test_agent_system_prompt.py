"""子代理系统提示词的素材装配顺序（SPEC-006）。"""

from __future__ import annotations

import json

from src.agent.system_prompt import (
    build_sub_system_prompt,
    extract_front_matter_description,
)


def test_extract_description_supports_quotes_and_missing_front_matter(tmp_path):
    quoted = tmp_path / "quoted.md"
    quoted.write_text('---\ndescription: "带引号"\n---\n正文', encoding="utf-8")
    plain = tmp_path / "plain.md"
    plain.write_text("---\ndescription: 无引号\n---\n", encoding="utf-8")
    none = tmp_path / "none.md"
    none.write_text("# 没有 front matter", encoding="utf-8")

    assert extract_front_matter_description(str(quoted)) == "带引号"
    assert extract_front_matter_description(str(plain)) == "无引号"
    assert extract_front_matter_description(str(none)) is None
    assert extract_front_matter_description(str(tmp_path / "missing.md")) is None


def _workspace(tmp_path):
    core = tmp_path / "core"
    skills = tmp_path / "skills"
    rules = tmp_path / "rules"
    workshop = tmp_path / "workshop"
    for directory in (core, skills, rules, workshop):
        directory.mkdir()

    (rules / "b.md").write_text("规则B", encoding="utf-8")
    (rules / "a.md").write_text("规则A", encoding="utf-8")
    (core / "SOUL.md").write_text("灵魂", encoding="utf-8")
    (core / "MEMORY.md").write_text("长期记忆", encoding="utf-8")
    (skills / "demo").mkdir()
    (skills / "demo" / "SKILL.md").write_text(
        "---\ndescription: 演示技能\n---\n", encoding="utf-8"
    )
    (workshop / "WORKSHOP.md").write_text(
        "---\ndescription: 演示作坊\n---\n", encoding="utf-8"
    )
    (core / "info.json").write_text(
        json.dumps({"skills": ["demo"], "workshops": [str(workshop)]}),
        encoding="utf-8",
    )
    return {
        "info_path": str(core / "info.json"),
        "skill_dir": str(skills),
        "rules_dir": str(rules),
        "soul_path": str(core / "SOUL.md"),
        "memory_path": str(core / "MEMORY.md"),
    }


def test_prompt_assembly_follows_rules_soul_skills_workshops_memory(tmp_path):
    prompt = build_sub_system_prompt(**_workspace(tmp_path))

    positions = [
        prompt.index("规则A"),
        prompt.index("规则B"),
        prompt.index("灵魂"),
        prompt.index("【核心技能档案】"),
        prompt.index("演示技能"),
        prompt.index("【常驻作坊 (Workshops)】"),
        prompt.index("演示作坊"),
        prompt.index("【系统长期记忆档案】"),
        prompt.index("长期记忆"),
    ]
    assert positions == sorted(positions)


def test_missing_material_produces_empty_prompt(tmp_path):
    prompt = build_sub_system_prompt(
        info_path=str(tmp_path / "nope.json"),
        skill_dir=str(tmp_path / "skills"),
        rules_dir=str(tmp_path / "rules"),
        soul_path=str(tmp_path / "soul.md"),
        memory_path=str(tmp_path / "memory.md"),
    )

    assert prompt == ""
