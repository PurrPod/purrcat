"""MCP 搜索实现 - 基于本地 Embedding + BM25 混合检索（线程安全单例）"""

import threading
from typing import List, Dict
import numpy as np

from rank_bm25 import BM25Okapi
from src.tool.search.semantic_utils import LocalEmbeddingSearcher, hybrid_tokenize
from src.tool.callmcp.schema_manager import load_cached_schemas


class MCPSearcher:
    """MCP 语义搜索器（线程安全单例）"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(MCPSearcher, cls).__new__(cls)
                cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self.tools = []
        self.corpus = []
        self.embedding_searcher = LocalEmbeddingSearcher()

        schemas = load_cached_schemas()

        for schema in schemas:
            server_name = schema.get("server", "")
            func = schema.get("function", {})
            tool_name = func.get("name", "")
            description = func.get("description", "")

            self.tools.append({
                "server_name": server_name,
                "tool_name": tool_name,
                "description": description
            })
            text_representation = f"{server_name} {tool_name} {tool_name.replace('_', ' ')} {description}"
            self.corpus.append(text_representation)

        if self.corpus:
            self.corpus_matrix = self.embedding_searcher.encode(self.corpus)
            
            tokenized_corpus = [hybrid_tokenize(doc) for doc in self.corpus]
            self.bm25 = BM25Okapi(tokenized_corpus)

    def search(self, query: str, max_results: int = 5) -> List[Dict]:
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

        top_k_indices = np.argsort(final_scores)[::-1][:max_results]

        results = []
        for idx in top_k_indices:
            score = float(final_scores[idx])
            if score > 0:
                result_item = self.tools[idx].copy()
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