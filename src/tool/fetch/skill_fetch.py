"""Skill 获取模块 - 加载和解析技能文件"""

from pathlib import Path
from typing import Dict
from .exceptions import SkillNotFoundError

DEFAULT_SKILL_PATH = Path("data/skill")


def _parse_skill_md(file_path: Path) -> Dict:
    """解析 SKILL.md 文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()
    
    metadata = {}
    content = text
    
    if text.startswith('---'):
        parts = text.split('---', 2)
        if len(parts) >= 3:
            frontmatter_str = parts[1]
            content = parts[2].strip()
            for line in frontmatter_str.split('\n'):
                line = line.strip()
                if line and ':' in line:
                    key, value = line.split(':', 1)
                    metadata[key.strip()] = value.strip()
    
    return {"metadata": metadata, "content": content}


def load_skill(name: str) -> tuple:
    """
    加载技能文件详情
    
    Args:
        name: 技能名称
    
    Returns:
        (skill_dict, error_message)
    """
    base_dir = Path(DEFAULT_SKILL_PATH)
    target_dir = base_dir / name
    md_file = target_dir / "SKILL.md"
    
    # 尝试按目录名查找
    if not md_file.exists():
        for item in base_dir.iterdir():
            if item.is_dir():
                dir_md = item / "SKILL.md"
                if dir_md.exists():
                    parsed = _parse_skill_md(dir_md)
                    if parsed["metadata"].get("name") == name:
                        md_file = dir_md
                        target_dir = item
                        break
    
    if not md_file.exists():
        # 抛出技能未找到异常
        raise SkillNotFoundError(name)
    
    try:
        parsed_data = _parse_skill_md(md_file)
        metadata = parsed_data["metadata"]
        content = parsed_data["content"]
        
        return {
            "name": metadata.get("name", name),
            "description": metadata.get("description", metadata.get("desc", "")),
            "content": content,
            "directory": str(target_dir)
        }, None
        
    except Exception as e:
        return None, f"解析技能文件失败: {str(e)}"