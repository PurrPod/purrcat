"""子代理系统提示词的素材装配（文件读取与拼接顺序在此集中）。"""

from __future__ import annotations

import os


def build_sub_system_prompt(
    *,
    rules_dir: str | None = None,
    soul_path: str | None = None,
    memory_path: str | None = None,
) -> str:
    """按固定顺序拼装子代理系统提示词：规则 → 灵魂 → 长期记忆。"""
    from src.utils.config import (
        AGENT_CORE_DIR,
        SOUL_MD_PATH,
        SYSTEM_RULES_DIR,
    )

    rules_dir = rules_dir or SYSTEM_RULES_DIR
    soul_path = soul_path or SOUL_MD_PATH
    memory_path = memory_path or os.path.join(AGENT_CORE_DIR, "MEMORY.md")

    soul_md, system_rules, memory_md = "", "", ""

    try:
        if os.path.exists(soul_path):
            with open(soul_path, "r", encoding="utf-8") as f:
                soul_md = f.read().strip()
        if os.path.exists(rules_dir):
            rule_files = sorted([f for f in os.listdir(rules_dir) if f.endswith(".md")])
            for rf in rule_files:
                with open(os.path.join(rules_dir, rf), "r", encoding="utf-8") as f:
                    system_rules += f.read().strip() + "\n\n"
            system_rules = system_rules.strip()
        if os.path.exists(memory_path):
            with open(memory_path, "r", encoding="utf-8") as f:
                memory_md = f.read().strip()
    except Exception as e:
        print(f"[Warn.SubAgent] Prompt 构建发生异常: {e}")

    combined = system_rules
    if soul_md:
        combined += f"\n\n---\n\n{soul_md}"
    if memory_md:
        combined += f"\n\n---\n\n# 【系统长期记忆档案】\n\n{memory_md}"
    return combined
