"""子代理系统提示词的素材装配顺序（SPEC-006）。"""

from __future__ import annotations

from src.agent.system_prompt import build_sub_system_prompt


def _workspace(tmp_path):
    core = tmp_path / "core"
    rules = tmp_path / "rules"
    for directory in (core, rules):
        directory.mkdir()

    (rules / "b.md").write_text("规则B", encoding="utf-8")
    (rules / "a.md").write_text("规则A", encoding="utf-8")
    (core / "SOUL.md").write_text("灵魂", encoding="utf-8")
    (core / "MEMORY.md").write_text("长期记忆", encoding="utf-8")
    return {
        "rules_dir": str(rules),
        "soul_path": str(core / "SOUL.md"),
        "memory_path": str(core / "MEMORY.md"),
    }


def test_prompt_assembly_follows_rules_soul_memory(tmp_path):
    prompt = build_sub_system_prompt(**_workspace(tmp_path))

    positions = [
        prompt.index("规则A"),
        prompt.index("规则B"),
        prompt.index("灵魂"),
        prompt.index("【系统长期记忆档案】"),
        prompt.index("长期记忆"),
    ]
    assert positions == sorted(positions)


def test_missing_material_produces_empty_prompt(tmp_path):
    prompt = build_sub_system_prompt(
        rules_dir=str(tmp_path / "rules"),
        soul_path=str(tmp_path / "soul.md"),
        memory_path=str(tmp_path / "memory.md"),
    )

    assert prompt == ""
