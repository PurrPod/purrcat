import os
from pathlib import Path
from config import BASE_DIR

def get_available_skills() -> list[str]:
    """
    获取与 tui/ 同级的 skill/ 目录下的所有文件夹名称作为可用 skill 列表。
    """
    try:
        # 当前文件在 src/util/skill_helper.py，向上找三层得到项目根目录
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent
        skill_dir = project_root / "skill"

        if not skill_dir.exists() or not skill_dir.is_dir():
            return []

        skills = []
        for item in skill_dir.iterdir():
            # 仅保留真实的文件夹，且过滤掉如 .git 等隐藏文件夹
            if item.is_dir() and not item.name.startswith("."):
                skills.append(item.name)

        # 字母顺序排序，方便用户查找
        return sorted(skills)
    except Exception as e:
        # 防御性编程：解析失败返回空列表
        return []