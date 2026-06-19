"""Skill 获取模块 - 加载和解析技能文件"""

import os
import shutil
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
        # ==== 新增逻辑：载入前从主库拉取最新的一份覆盖进沙盒中 ====
        source_dir = f"./skills/{name}"
        target_dir = f"./agent_vm/skills/{name}"

        # 只要主库存在该技能，就强制覆盖沙盒里的缓存，保证 Agent 在沙盒里执行时是最新的
        if os.path.exists(source_dir):
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir, ignore_errors=True)
            os.makedirs(os.path.dirname(target_dir), exist_ok=True)
            shutil.copytree(source_dir, target_dir)
        # =======================================================

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
