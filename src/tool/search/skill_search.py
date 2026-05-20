"""Skill 搜索模块 - 基于本地 Embedding + BM25 混合检索（线程安全单例）"""

import threading
from pathlib import Path
from typing import Dict, List

import numpy as np
from rank_bm25 import BM25Okapi

from src.tool.search.semantic_utils import LocalEmbeddingSearcher, hybrid_tokenize
from src.utils.config import SKILL_DIR
from src.utils.skill_helper import _find_skill_md_file, _parse_skill_md


class SkillSearcher:
    """Skill 语义搜索器（线程安全单例，支持原子级热更新）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, skill_dir: str = SKILL_DIR):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SkillSearcher, cls).__new__(cls)
                cls._instance.skills = []
                cls._instance.corpus = []
                cls._instance.corpus_matrix = None
                cls._instance.bm25 = None
                cls._instance.embedding_searcher = LocalEmbeddingSearcher()
                cls._instance._initialize(skill_dir)
        return cls._instance

    def _initialize(self, skill_dir: str):
        """局部构建索引，防止并发冲突"""
        temp_skills = []
        temp_corpus = []

        skill_path = Path(skill_dir)
        if skill_path.exists() and skill_path.is_dir():
            for item in skill_path.iterdir():
                if item.is_dir():
                    md_file = item / "SKILL.md"
                    if md_file.exists():
                        parsed_data = _parse_skill_md(md_file)
                        metadata = parsed_data["metadata"]
                        name = metadata.get("name", item.name)
                        desc = metadata.get("description", metadata.get("desc", ""))
                        content = parsed_data.get("content", "")

                        temp_skills.append(
                            {"name": name, "description": desc, "dir_name": item.name}
                        )
                        text_representation = f"{name} {desc} {content}"
                        temp_corpus.append(text_representation)

        if temp_corpus:
            temp_corpus_matrix = self.embedding_searcher.encode(temp_corpus)
            tokenized_corpus = [hybrid_tokenize(doc) for doc in temp_corpus]
            temp_bm25 = BM25Okapi(tokenized_corpus)

            self.skills = temp_skills
            self.corpus = temp_corpus
            self.corpus_matrix = temp_corpus_matrix
            self.bm25 = temp_bm25
            print(f"✅ SkillSearcher 内存索引已更新 (共 {len(self.skills)} 个技能)")

    def reload_index(self, skill_dir: str = SKILL_DIR):
        """暴露给外部调用的热更新接口"""
        with self._lock:
            print("🔄 正在扫描本地文件，重载 SkillSearcher 内存索引...")
            self._initialize(skill_dir)

    def search(self, query: str, top_k: int = 3) -> List[Dict]:
        """执行搜索并返回匹配度最高的前 K 个技能"""
        # 【修复】加锁防止查询时遭遇热更新导致数据结构断裂
        with self._lock:
            if not self.corpus:
                return []

            # 获取引用快照以防止后续计算时被修改
            current_corpus = self.corpus
            current_matrix = self.corpus_matrix
            current_bm25 = self.bm25
            current_skills = self.skills

        # 【优化】相似度计算可以在锁外执行（使用局部变量快照）
        query_vector = self.embedding_searcher.encode([query])
        dense_scores = self.embedding_searcher.calculate_similarity(
            query_vector, current_matrix
        )

        tokenized_query = hybrid_tokenize(query)
        raw_bm25_scores = current_bm25.get_scores(tokenized_query)

        max_bm25 = max(raw_bm25_scores) if raw_bm25_scores.size > 0 else 0
        if max_bm25 > 0:
            bm25_scores = [score / max_bm25 for score in raw_bm25_scores]
        else:
            bm25_scores = [0] * len(current_corpus)

        alpha_dense = 0.7
        alpha_sparse = 0.3

        final_scores = []
        for i in range(len(current_corpus)):
            combined_score = (dense_scores[i] * alpha_dense) + (
                bm25_scores[i] * alpha_sparse
            )
            final_scores.append(combined_score)

        final_scores = np.array(final_scores)
        top_k_indices = np.argsort(final_scores)[::-1][:top_k]

        results = []
        for idx in top_k_indices:
            score = float(final_scores[idx])
            if score > 0:
                results.append({"score": round(score, 4), "skill": current_skills[idx]})

        return results

def reload_skill_index():
    skill_searcher = SkillSearcher(SKILL_DIR)
    skill_searcher.reload_index()


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


