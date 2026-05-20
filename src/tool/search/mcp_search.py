"""MCP 搜索实现 - 基于本地 Embedding + BM25 混合检索（线程安全单例）"""

import threading
from typing import Dict, List

import numpy as np
from rank_bm25 import BM25Okapi

from src.tool.callmcp.schema_manager import load_cached_schemas
from src.tool.search.semantic_utils import LocalEmbeddingSearcher, hybrid_tokenize


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
        """局部构建索引，防止并发冲突"""
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
            text_representation = (
                f"{server_name} {tool_name} {tool_name.replace('_', ' ')} {description}"
            )
            temp_corpus.append(text_representation)

        if temp_corpus:
            temp_corpus_matrix = self.embedding_searcher.encode(temp_corpus)
            tokenized_corpus = [hybrid_tokenize(doc) for doc in temp_corpus]
            temp_bm25 = BM25Okapi(tokenized_corpus)

            self.tools = temp_tools
            self.corpus = temp_corpus
            self.corpus_matrix = temp_corpus_matrix
            self.bm25 = temp_bm25
            print(f"✅ MCPSearcher 内存索引已更新 (共 {len(self.tools)} 个工具)")

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

            # 获取引用快照以防止后续计算时被修改
            current_corpus = self.corpus
            current_matrix = self.corpus_matrix
            current_bm25 = self.bm25
            current_tools = self.tools

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

        top_k_indices = np.argsort(final_scores)[::-1][:max_results]

        results = []
        for idx in top_k_indices:
            score = float(final_scores[idx])
            if score > 0:
                result_item = current_tools[idx].copy()
                result_item["score"] = round(score, 4)
                results.append(result_item)

        return results


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