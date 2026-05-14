"""Skill 搜索模块 - 基于本地 Embedding + BM25 混合检索（线程安全单例）"""

import threading
from pathlib import Path
from typing import List, Dict, Any

import numpy as np

from rank_bm25 import BM25Okapi
from src.utils.config import SKILL_DIR
from src.utils.skill_helper import _parse_skill_md, _find_skill_md_file
from src.tool.search.semantic_utils import LocalEmbeddingSearcher, hybrid_tokenize


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
            
            tokenized_corpus = [hybrid_tokenize(doc) for doc in self.corpus]
            self.bm25 = BM25Okapi(tokenized_corpus)

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
        dense_scores = self.embedding_searcher.calculate_similarity(query_vector, self.corpus_matrix)

        tokenized_query = hybrid_tokenize(query)
        raw_bm25_scores = self.bm25.get_scores(tokenized_query)
        
        max_bm25 = max(raw_bm25_scores) if raw_bm25_scores.size > 0 else 0
        if max_bm25 > 0:
            bm25_scores = [score / max_bm25 for score in raw_bm25_scores]
        else:
            bm25_scores = [0] * len(self.corpus)

        alpha_dense = 0.7
        alpha_sparse = 0.3

        final_scores = []
        for i in range(len(self.corpus)):
            combined_score = (dense_scores[i] * alpha_dense) + (bm25_scores[i] * alpha_sparse)
            final_scores.append(combined_score)

        final_scores = np.array(final_scores)
        top_k_indices = np.argsort(final_scores)[::-1][:top_k]

        results = []
        for idx in top_k_indices:
            score = float(final_scores[idx])
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
    md_file, _ = _find_skill_md_file(name)
    if not md_file.exists():
        raise FileNotFoundError(f"找不到技能: {name}")

    parsed_data = _parse_skill_md(md_file)
    return {
        "name": parsed_data["metadata"].get("name", name),
        "description": parsed_data["metadata"].get("description", ""),
        "content": parsed_data["content"],
        "path": str(md_file)
    }