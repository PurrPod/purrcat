"""MCP 搜索实现 - 基于本地 Embedding + BM25 混合检索（线程安全单例）"""

import threading
from typing import Dict, List

import numpy as np

from src.tool.callmcp.schema_manager import load_cached_schemas
from src.tool.search import _shared
from src.tool.search.semantic_utils import LocalEmbeddingSearcher


class MCPSearcher:
    """MCP 语义搜索器（线程安全单例，支持原子级热更新）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(MCPSearcher, cls).__new__(cls)
                cls._instance.tools = []
                cls._instance.corpus = []
                cls._instance.corpus_matrix = None
                cls._instance.bm25 = None
                cls._instance.embedding_searcher = LocalEmbeddingSearcher()
                cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """🌟 重构：仅加载元数据，速度极快"""
        temp_tools = []
        temp_corpus = []

        schemas = load_cached_schemas()

        for schema in schemas:
            server_name = schema.get("server", "")
            func = schema.get("function", {})
            tool_name = func.get("name", "")
            description = func.get("description", "")

            temp_tools.append(
                {
                    "server_name": server_name,
                    "tool_name": tool_name,
                    "description": description,
                }
            )
            temp_corpus.append(
                _shared.mcp_document_text(server_name, tool_name, description)
            )

        self.tools = temp_tools
        self.corpus = temp_corpus
        # 不在这里算向量！
        print(f"✅ MCPSearcher 元数据已加载 (共 {len(self.tools)} 个工具)")

    def build_vectors_in_background(self):
        """🌟 新增：由后台事件循环触发的缓慢操作"""
        with self._lock:
            if not self.corpus:
                return
            print(
                f"⏳ [Background] 正在为 {len(self.tools)} 个 MCP 工具构建向量矩阵..."
            )
            self.corpus_matrix, self.bm25 = _shared.build_hybrid_index(
                self.embedding_searcher, self.corpus
            )
            print("[*] MCP 向量矩阵构建完毕。")

    def reload_index(self):
        """暴露给外部调用的热更新接口"""
        with self._lock:
            print("🔄 正在从本地缓存重载 MCPSearcher 内存索引...")
            self._initialize()

    def search(self, query: str, max_results: int = 5) -> List[Dict]:
        # 【修复】加锁防止查询时遭遇热更新导致数据结构断裂
        # 使用局部变量快照，将计算密集型操作移到锁外
        with self._lock:
            if not self.corpus:
                return []

            if self.corpus_matrix is None or self.bm25 is None:
                print("⏳ [JIT] 检测到索引未就绪，正在强制同步构建...")
                self.corpus_matrix, self.bm25 = _shared.build_hybrid_index(
                    self.embedding_searcher, self.corpus
                )
                print("✅ [JIT] 同步构建完成！")

            # 获取引用快照以防止后续计算时被修改
            current_matrix = self.corpus_matrix
            current_bm25 = self.bm25
            current_tools = self.tools

        # 【优化】相似度计算可以在锁外执行（使用局部变量快照）
        final_scores, top_k_indices = _shared.score_top_k(
            self.embedding_searcher,
            query,
            current_matrix,
            current_bm25,
            max_results,
            clamp_negative=False,
        )

        results = []
        for idx in top_k_indices:
            score = float(final_scores[idx])
            if score > 0:
                result_item = current_tools[idx].copy()
                result_item["score"] = round(score, 4)
                results.append(result_item)

        return results

    def simulate_trigger(
        self,
        query: str,
        sandbox_server_name: str,
        sandbox_tools: list,
        expected_tool_name: str,
        top_k: int = 5,
        threshold: float = 0.3,
    ) -> dict:
        """
        MCP 触发测试：将沙盒服务器下解析出的多个工具注入全局快照，
        检索指定的 expected_tool_name 是否能成功杀入 Top K 并达到阈值。
        """
        import copy

        with self._lock:
            # 1. 抓取当前真实环境快照 (不修改原数据)
            temp_corpus = self.corpus.copy() if self.corpus else []
            temp_tools = copy.deepcopy(self.tools) if self.tools else []
            # 复制矩阵，避免并发污染
            temp_matrix = (
                self.corpus_matrix.copy()
                if self.corpus_matrix is not None
                else np.empty((0, 0))
            )

        # 2. 批量注入沙盒服务器的 tools
        target_idx = -1  # 记录我们期望命中的那个工具在 temp_tools 中的最终索引

        for tool in sandbox_tools:
            tool_name = tool.get("name", "")
            desc = tool.get("description", "")
            text_repr = _shared.mcp_document_text(sandbox_server_name, tool_name, desc)
            vector = self.embedding_searcher.encode([text_repr])

            # 寻找快照中是否已有同名工具 (如果是覆盖升级)
            existing_idx = -1
            for i, t in enumerate(temp_tools):
                if (
                    t["server_name"] == sandbox_server_name
                    and t["tool_name"] == tool_name
                ):
                    existing_idx = i
                    break

            if existing_idx != -1:
                temp_corpus[existing_idx] = text_repr
                temp_tools[existing_idx] = {
                    "server_name": sandbox_server_name,
                    "tool_name": tool_name,
                    "description": desc,
                }
                if temp_matrix.size > 0:
                    temp_matrix[existing_idx] = vector[0]
                if tool_name == expected_tool_name:
                    target_idx = existing_idx
            else:
                # 全新工具，追加
                temp_corpus.append(text_repr)
                temp_tools.append(
                    {
                        "server_name": sandbox_server_name,
                        "tool_name": tool_name,
                        "description": desc,
                    }
                )
                if temp_matrix.size > 0:
                    temp_matrix = np.vstack([temp_matrix, vector])
                else:
                    temp_matrix = vector

                if tool_name == expected_tool_name:
                    target_idx = len(temp_corpus) - 1

        # 如果反例测试（expected_tool_name 为 null/None）
        if not expected_tool_name:
            target_idx = -1

        # 3. 执行真实的混合检索打分
        temp_bm25 = _shared.build_bm25(temp_corpus)
        final_scores, top_k_indices = _shared.score_top_k(
            self.embedding_searcher,
            query,
            temp_matrix,
            temp_bm25,
            top_k,
            clamp_negative=False,
        )

        # 4. 激发状态判定
        is_triggered, rank, score = _shared.evaluate_rank(
            final_scores, top_k_indices, target_idx, threshold
        )

        competitors = [
            f"[{temp_tools[idx]['server_name']}]{temp_tools[idx]['tool_name']} (得分: {round(float(final_scores[idx]), 4)})"
            for idx in top_k_indices
            if idx != target_idx
        ]

        return {
            "is_triggered": is_triggered,
            "score": round(float(score), 4) if target_idx != -1 else 0.0,
            "rank": rank,
            "threshold": threshold,
            "competitors": competitors,
        }


def mcp_search(query: str, max_results: int = 5) -> tuple:
    """外部调用的门面函数"""
    try:
        searcher = MCPSearcher()
        results = searcher.search(query, max_results)
        return results, None
    except Exception as e:
        return [], f"MCP搜索异常: {e}"


def reload_mcp_index():
    """MCP索引热更新入口"""
    searcher = MCPSearcher()
    searcher.reload_index()


def rebuild_vectors_async():
    """后台线程重建向量矩阵：刷新索引后立即调用，避免首次搜索 JIT 同步构建卡顿"""
    import threading

    def _worker():
        try:
            MCPSearcher().build_vectors_in_background()
        except Exception as e:
            print(f"[-] MCP 向量后台构建失败: {e}")

    threading.Thread(target=_worker, daemon=True, name="MCP-Vector-Build").start()
