"""Skill 获取模块 - 加载和解析技能文件"""

import os
import shutil
import stat
import time
from src.utils.config import SKILL_DIR
from src.utils.skill_helper import _find_skill_md_file, _parse_skill_md, get_skill_info
from .exceptions import SkillNotFoundError


def _force_rmtree(path: str, max_retries: int = 3, retry_delay: float = 0.1):
    """
    强制删除目录，处理 Windows 上的只读属性和文件锁定问题

    Args:
        path: 要删除的目录路径
        max_retries: 最大重试次数
        retry_delay: 重试间隔（秒）
    """

    def _on_exc(exc):
        os.chmod(exc.filename, stat.S_IWRITE)
        return True

    for attempt in range(max_retries):
        try:
            shutil.rmtree(path, onexc=_on_exc)
            return
        except PermissionError:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                raise


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
        source_dir = os.path.join(SKILL_DIR, name)
        target_dir = f"./agent_vm/skills/{name}"

        # 只要主库存在该技能，就强制覆盖沙盒里的缓存，保证 Agent 在沙盒里执行时是最新的
        if os.path.exists(source_dir):
            os.makedirs(os.path.dirname(target_dir), exist_ok=True)
            if os.path.exists(target_dir):
                _force_rmtree(target_dir)
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
