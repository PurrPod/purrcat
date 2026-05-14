import os
from pathlib import Path
from src.utils.config import SKILL_DIR


def get_available_skills() -> list[str]:
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


def _parse_skill_md(file_path: Path) -> dict:
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


def _find_skill_md_file(skill_name: str) -> tuple:
    base_dir = Path(SKILL_DIR)
    target_dir = base_dir / skill_name
    md_file = target_dir / "SKILL.md"

    if not md_file.exists():
        for item in base_dir.iterdir():
            if item.is_dir():
                dir_md = item / "SKILL.md"
                if dir_md.exists():
                    parsed = _parse_skill_md(dir_md)
                    if parsed["metadata"].get("name") == skill_name:
                        md_file = dir_md
                        target_dir = item
                        break

    return md_file, target_dir


def get_skill_content(skill_name: str) -> str:
    md_file, _ = _find_skill_md_file(skill_name)
    if not md_file.exists():
        return ""

    parsed_data = _parse_skill_md(md_file)
    return parsed_data["content"]


def get_skill_info(skill_name: str) -> dict:
    md_file, target_dir = _find_skill_md_file(skill_name)
    if not md_file.exists():
        return {}

    parsed_data = _parse_skill_md(md_file)
    metadata = parsed_data["metadata"]

    return {
        "name": metadata.get("name", skill_name),
        "description": metadata.get("description", metadata.get("desc", "")),
    }

