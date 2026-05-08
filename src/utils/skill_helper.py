import os
from src.utils.config import SKILL_DIR

def get_available_skills() -> list[str]:
    """
    获取与 tui/ 同级的 skill/ 目录下的所有文件夹名称作为可用 skill 列表。
    """
    try:
        if not os.path.exists(SKILL_DIR) or not os.path.isdir(SKILL_DIR):
            return []

        skills = []
        for item in os.listdir(SKILL_DIR):
            item_path = os.path.join(SKILL_DIR, item)
            if os.path.isdir(item_path) and not item.startswith("."):
                skills.append(item)

        return sorted(skills)
    except Exception as e:
        return []