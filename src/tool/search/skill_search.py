"""Skill 搜索模块 - 基于本地 Embedding 语义匹配（线程安全单例）"""

import threading
from pathlib import Path
from typing import List, Dict, Any

import numpy as np


from src.utils.config import SKILL_DIR
from src.tool.search.semantic_utils import LocalEmbeddingSearcher


def _parse_skill_md(file_path: Path) -> Dict[str, Any]:
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


class SkillSearcher:
    """Skill 语义搜索器（线程安全单例，语料与矩阵驻留内存）"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, skill_dir: str = SKILL_DIR):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SkillSearcher, cls).__new__(cls)
                cls._instance._initialize(skill_dir)
        return cls._instance

    def _initialize(self, skill_dir: str):
        self.skills = []
        self.corpus = []
        self.embedding_searcher = LocalEmbeddingSearcher()
        self._load_skills(Path(skill_dir))

        if self.corpus:
            self.corpus_matrix = self.embedding_searcher.encode(self.corpus)

    def _load_skills(self, skill_dir: Path):
        """遍历 Skill 目录，解析 SKILL.md"""
        if not skill_dir.exists() or not skill_dir.is_dir():
            return

        for item in skill_dir.iterdir():
            if item.is_dir():
                md_file = item / "SKILL.md"
                if md_file.exists():
                    parsed_data = _parse_skill_md(md_file)
                    metadata = parsed_data["metadata"]
                    name = metadata.get("name", item.name)
                    desc = metadata.get("description", metadata.get("desc", ""))
                    content = parsed_data.get("content", "")

                    self.skills.append({
                        "name": name,
                        "description": desc,
                        "dir_name": item.name
                    })
                    text_representation = f"{name} {desc} {content}"
                    self.corpus.append(text_representation)

    def search(self, query: str, top_k: int = 3) -> List[Dict]:
        """执行搜索并返回匹配度最高的前 K 个技能"""
        if not self.corpus:
            return []

        query_vector = self.embedding_searcher.encode([query])
        similarities = self.embedding_searcher.calculate_similarity(query_vector, self.corpus_matrix)
        top_k_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_k_indices:
            score = float(similarities[idx])
            if score > 0:
                results.append({
                    "score": round(score, 4),
                    "skill": self.skills[idx]
                })

        return results


def search_skills(query: str, top_k: int = 3) -> tuple:
    """
    搜索技能

    Args:
        query: 搜索查询词
        top_k: 返回前 K 个结果

    Returns:
        (results, error_message)
    """
    try:
        skill_searcher = SkillSearcher(SKILL_DIR)
        results = skill_searcher.search(query, top_k)
        return results, None
    except Exception as e:
        return [], f"Skill搜索异常: {e}"


def load_skill(name: str) -> dict:
    """
    加载技能文件详情

    Args:
        name: 技能名称

    Returns:
        技能详情字典
    """
    base_dir = Path(SKILL_DIR)
    target_dir = base_dir / name
    md_file = target_dir / "SKILL.md"

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
        raise FileNotFoundError(f"找不到技能: {name}")

    parsed_data = _parse_skill_md(md_file)
    skill_info = {
        "name": parsed_data["metadata"].get("name", name),
        "description": parsed_data["metadata"].get("description", ""),
        "content": parsed_data["content"],
        "path": str(md_file)
    }

    return skill_info