"""Skill 搜索模块 - 基于本地 Embedding + BM25 混合检索（线程安全单例）"""

import threading
from pathlib import Path
from typing import Dict, List

import numpy as np

from src.tool.search import _shared
from src.tool.search.semantic_utils import LocalEmbeddingSearcher
from src.utils.config import SKILL_DIR
from src.utils.skill_helper import _parse_skill_md


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
        """🌟 重构：仅加载元数据，速度极快"""
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
                        temp_corpus.append(
                            _shared.skill_document_text(name, desc, content)
                        )

        self.skills = temp_skills
        self.corpus = temp_corpus
        # 不在这里算向量！
        print(f"✅ SkillSearcher 元数据已加载 (共 {len(self.skills)} 个技能)")

    def build_vectors_in_background(self):
        """🌟 新增：由后台事件循环触发的缓慢操作"""
        with self._lock:
            if not self.corpus:
                return
            print(f"[+] 正在为 {len(self.skills)} 个 Skill 构建向量矩阵...")
            self.corpus_matrix, self.bm25 = _shared.build_hybrid_index(
                self.embedding_searcher, self.corpus
            )
            print("[*] Skill 向量矩阵构建完毕。")

    def reload_index(self, skill_dir: str = SKILL_DIR):
        """暴露给外部调用的热更新接口"""
        with self._lock:
            print("[+] 正在扫描本地文件，重载 SkillSearcher 内存索引...")
            self._initialize(skill_dir)

    def search(self, query: str, top_k: int = 3) -> List[Dict]:
        """执行搜索并返回匹配度最高的前 K 个技能"""
        # 【修复】加锁防止查询时遭遇热更新导致数据结构断裂
        with self._lock:
            if not self.corpus:
                return []

            if self.corpus_matrix is None or self.bm25 is None:
                print("[+] 检测到索引未就绪，正在强制同步构建...")
                self.corpus_matrix, self.bm25 = _shared.build_hybrid_index(
                    self.embedding_searcher, self.corpus
                )
                print("[*] 同步构建完成！")

            # 获取引用快照以防止后续计算时被修改
            current_matrix = self.corpus_matrix
            current_bm25 = self.bm25
            current_skills = self.skills

        # 【优化】相似度计算可以在锁外执行（使用局部变量快照）
        final_scores, top_k_indices = _shared.score_top_k(
            self.embedding_searcher,
            query,
            current_matrix,
            current_bm25,
            top_k,
            clamp_negative=True,
        )

        results = []
        for idx in top_k_indices:
            score = float(final_scores[idx])
            if score > 0:
                results.append({"score": round(score, 4), "skill": current_skills[idx]})

        return results

    def simulate_trigger(
        self, query: str, sandbox_skill: dict, top_k: int = 3, threshold: float = 0.3
    ) -> dict:
        """
        触发测试：临时将沙盒技能以"影子节点"形式注入全局语料快照中，
        进行真实的混合检索，评估其是否能击败其他真实技能被成功激发。
        """
        import copy

        with self._lock:
            # 1. 抓取当前真实环境快照 (不修改原数据)
            temp_corpus = self.corpus.copy() if self.corpus else []
            temp_skills = copy.deepcopy(self.skills) if self.skills else []
            # 复制矩阵，避免并发污染
            temp_matrix = (
                self.corpus_matrix.copy()
                if self.corpus_matrix is not None
                else np.empty((0, 0))
            )

        # 2. 组装沙盒技能文本与计算向量
        sandbox_name = sandbox_skill.get("name", "")
        sandbox_desc = sandbox_skill.get("description", "")
        sandbox_content = sandbox_skill.get("content", "")
        sandbox_text = _shared.skill_document_text(
            sandbox_name, sandbox_desc, sandbox_content
        )

        sandbox_vector = self.embedding_searcher.encode([sandbox_text])

        # 3. 寻找并替换旧版，或追加新版
        target_idx = -1
        for i, s in enumerate(temp_skills):
            if s["name"] == sandbox_name:
                target_idx = i
                break

        if target_idx != -1:
            # 覆盖主库中现存的旧版本
            temp_corpus[target_idx] = sandbox_text
            temp_skills[target_idx] = sandbox_skill
            if temp_matrix.size > 0:
                temp_matrix[target_idx] = sandbox_vector[0]
        else:
            # 这是一个全新的技能，追加到快照末尾
            temp_corpus.append(sandbox_text)
            temp_skills.append(sandbox_skill)
            if temp_matrix.size > 0:
                temp_matrix = np.vstack([temp_matrix, sandbox_vector])
            else:
                temp_matrix = sandbox_vector

        # 4. 执行真实的混合检索打分
        # 重新初始化轻量级 BM25 (由于语料少，耗时极短)
        temp_bm25 = _shared.build_bm25(temp_corpus)
        # 同 search()：BM25 负分截断到 0，避免 log1p 产生 nan
        final_scores, top_k_indices = _shared.score_top_k(
            self.embedding_searcher,
            query,
            temp_matrix,
            temp_bm25,
            top_k,
            clamp_negative=True,
        )

        # 5. 激发状态判定
        # 注意 target_idx 在新技能追加时，等于 len(temp_corpus) - 1
        if target_idx == -1:
            target_idx = len(temp_corpus) - 1

        is_triggered, rank, trigger_score = _shared.evaluate_rank(
            final_scores, top_k_indices, target_idx, threshold
        )

        return {
            "is_triggered": is_triggered,
            "score": round(float(trigger_score), 4),
            "rank": rank,
            "threshold": threshold,
            "competitors": [
                temp_skills[idx]["name"] for idx in top_k_indices if idx != target_idx
            ],
        }


def reload_skill_index():
    skill_searcher = SkillSearcher(SKILL_DIR)
    skill_searcher.reload_index()


def rebuild_skill_vectors_async():
    """后台线程重建向量矩阵：刷新索引后立即调用，避免首次搜索 JIT 同步构建卡顿"""
    import threading

    def _worker():
        try:
            SkillSearcher(SKILL_DIR).build_vectors_in_background()
        except Exception as e:
            print(f"[-] Skill 向量后台构建失败: {e}")

    threading.Thread(target=_worker, daemon=True, name="Skill-Vector-Build").start()


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
