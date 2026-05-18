"""Skill 获取模块 - 加载和解析技能文件"""

from src.utils.skill_helper import _find_skill_md_file, _parse_skill_md, get_skill_info

from .exceptions import SkillNotFoundError


def load_skill(name: str) -> tuple:
    """
    加载技能文件详情

    Args:
        name: 技能名称

    Returns:
        (skill_dict, error_message)
    """
    try:
        skill_info = get_skill_info(name)
        if not skill_info:
            raise SkillNotFoundError(name)

        md_file, sandbox_dir = _find_skill_md_file(name)
        parsed_data = _parse_skill_md(md_file)
        skill_info["content"] = parsed_data["content"]
        skill_info["directory"] = str(sandbox_dir)

        return skill_info, None
    except SkillNotFoundError:
        raise
    except Exception as e:
        return None, f"解析技能文件失败: {str(e)}"
