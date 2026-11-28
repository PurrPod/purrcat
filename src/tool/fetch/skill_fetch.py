"""Skill 获取模块 - 加载和解析技能文件"""

import os
import shutil
import stat
import time
from src.utils.config import AGENT_VM_DIR
from src.utils.skill_helper import _find_skill_md_file, _parse_skill_md
from .exceptions import SkillNotFoundError


def _force_rmtree(path: str, max_retries: int = 3, retry_delay: float = 0.1):
    """
    强制删除目录，处理 Windows 上的只读属性和文件锁定问题

    Args:
        path: 要删除的目录路径
        max_retries: 最大重试次数
        retry_delay: 重试间隔（秒）
    """

    def _on_exc(func, path, exc):
        # onexc 回调签名为 (func, path, exc)：去掉只读属性后重试失败的那一步
        try:
            os.chmod(path, stat.S_IWRITE)
        except OSError:
            pass
        func(path)

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
        name: 技能名称（frontmatter name，可能与目录名不同）

    Returns:
        (skill_dict, error_message)
    """
    try:
        # 先定位真实主库目录：技能目录名可能与 frontmatter name 不同
        # （如 soft-skill 目录内技能的 name 是 high-end-visual-design）
        md_file, sandbox_dir = _find_skill_md_file(name)
        if not md_file.exists():
            raise SkillNotFoundError(name)

        # ==== 载入前从主库拉取最新的一份覆盖进沙盒中 ====
        # 以定位到的真实目录为复制源，按技能名落到沙盒（与 sandbox_dir 对齐），
        # 强制覆盖沙盒里的缓存，保证 Agent 在沙盒里执行时是最新的
        source_dir = str(md_file.parent)
        target_dir = os.path.join(AGENT_VM_DIR, "skills", name)

        os.makedirs(os.path.dirname(target_dir), exist_ok=True)
        if os.path.exists(target_dir):
            _force_rmtree(target_dir)
        shutil.copytree(source_dir, target_dir)
        # =======================================================

        parsed_data = _parse_skill_md(md_file)
        metadata = parsed_data["metadata"]

        return {
            "name": metadata.get("name", name),
            "description": metadata.get("description", metadata.get("desc", "")),
            "content": parsed_data["content"],
            "directory": str(sandbox_dir),
        }, None
    except SkillNotFoundError:
        raise
    except Exception as e:
        return None, f"解析技能文件失败: {str(e)}"
