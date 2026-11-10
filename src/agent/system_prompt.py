"""子代理系统提示词的素材装配（文件读取与拼接顺序在此集中）。"""

from __future__ import annotations

import json
import os


def extract_front_matter_description(file_path: str) -> str | None:
    """读取 Markdown front-matter 里的 description 字段。"""
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            in_front_matter = False
            for line in f:
                line = line.strip()
                if line == "---":
                    if not in_front_matter:
                        in_front_matter = True
                        continue
                    break
                if in_front_matter and line.lower().startswith("description:"):
                    val = line.split(":", 1)[1].strip()
                    if (val.startswith('"') and val.endswith('"')) or (
                        val.startswith("'") and val.endswith("'")
                    ):
                        val = val[1:-1]
                    return val
    except Exception:
        pass
    return None


def _skill_lines(info_data: dict, skill_dir: str) -> str:
    skills = info_data.get("skills", [])
    if not skills:
        return ""
    text = "以下是核心skill，所有的skill以本清单为第一优先级，请在工作过程中遇到对应任务就使用Fetch工具进行调用！！！\n"
    for skill in skills:
        desc = extract_front_matter_description(
            os.path.join(skill_dir, skill, "SKILL.md")
        )
        if desc:
            text += f"- {skill}:{desc}\n"
        else:
            text += f"- {skill}（技能加载失败，可能未安装）\n"
    text += "对于本清单以外的其它普通skill，请使用Search工具进行检索和发现。\n"
    return text


def _workshop_lines(info_data: dict) -> str:
    workshops = info_data.get("workshops", [])
    if not workshops:
        return ""
    text = (
        "以下是系统常驻作坊，请在收到特定任务的时候进入对应的文件夹内读取对应项目的"
        "AGENTS.md或WORKSHOP.md进行工作，\n"
    )
    for ws in workshops:
        desc = extract_front_matter_description(os.path.join(ws, "WORKSHOP.md"))
        if desc:
            text += f"- {ws}:{desc}\n"
        else:
            text += f"- {ws}（作坊加载失败，可能未找到WORKSHOP.md）\n"
    text += "如无相关作坊，直接在沙盒内工作即可\n"
    return text


def build_sub_system_prompt(
    *,
    info_path: str | None = None,
    skill_dir: str | None = None,
    rules_dir: str | None = None,
    soul_path: str | None = None,
    memory_path: str | None = None,
) -> str:
    """按固定顺序拼装子代理系统提示词：规则 → 灵魂 → 技能 → 作坊 → 长期记忆。"""
    from src.utils.config import (
        AGENT_CORE_DIR,
        SKILL_DIR,
        SOUL_MD_PATH,
        SYSTEM_RULES_DIR,
    )

    info_path = info_path or os.path.join(AGENT_CORE_DIR, "info.json")
    skill_dir = skill_dir or SKILL_DIR
    rules_dir = rules_dir or SYSTEM_RULES_DIR
    soul_path = soul_path or SOUL_MD_PATH
    memory_path = memory_path or os.path.join(AGENT_CORE_DIR, "MEMORY.md")

    soul_md, system_rules, memory_md = "", "", ""
    skills_info, workshops_info = "", ""

    try:
        if os.path.exists(info_path):
            with open(info_path, "r", encoding="utf-8") as f:
                info_data = json.load(f)
            skills_info = _skill_lines(info_data, skill_dir)
            workshops_info = _workshop_lines(info_data)

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
    if skills_info:
        combined += f"\n\n---\n\n# 【核心技能档案】\n\n{skills_info}"
    if workshops_info:
        combined += f"\n\n---\n\n# 【常驻作坊 (Workshops)】\n\n{workshops_info}"
    if memory_md:
        combined += f"\n\n---\n\n# 【系统长期记忆档案】\n\n{memory_md}"
    return combined
