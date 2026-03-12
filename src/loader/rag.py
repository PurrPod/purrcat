import os
import json
import numpy as np
try:
    import faiss
except ImportError:
    faiss = None
import jieba
import logging
from rank_bm25 import BM25Okapi
from typing import List, Dict, Optional, Any
from sentence_transformers import SentenceTransformer

jieba.setLogLevel(logging.INFO)


class VectorDB:
    """单个知识库的内存缓冲载体"""
    def __init__(self, db_name: str, base_dir: str):
        self.db_name = db_name
        self.db_path = os.path.join(base_dir, db_name)
        self.index: Optional[Any] = None
        self.documents: List[Dict] = []
        self.bm25: Optional[BM25Okapi] = None
        self.doc_lookup: Dict[tuple, str] = {}
        self._load_from_disk()

    def _load_from_disk(self):
        if faiss is None:
            print(f"⚠️ 警告: faiss 未安装，无法加载知识库 '{self.db_name}'。")
            return
        index_file = f"{self.db_path}/{self.db_name}.index"
        docs_file = f"{self.db_path}/{self.db_name}.json"
        if not os.path.exists(index_file):
            index_file = f"{self.db_path}\\{self.db_name}.index"
            docs_file = f"{self.db_path}\\{self.db_name}.json"
        if not os.path.exists(index_file) or not os.path.exists(docs_file):
            print(f"⚠️ 警告: 知识库 '{self.db_name}' 文件不完整，加载失败。")
            # 失败就去运行词向量嵌入，为了保持主体项目简洁，把这部分逻辑放到项目以外了。
            return
        self.index = faiss.read_index(index_file)
        with open(docs_file, 'r', encoding='utf-8') as f:
            self.documents = json.load(f)
            for doc in self.documents:
                source = doc.get("meta", {}).get("source", "unknown")
                chunk_id = doc.get("meta", {}).get("chunk_id", -1)
                self.doc_lookup[(source, chunk_id)] = doc["text"]
        if self.documents:
            tokenized_corpus = [list(jieba.cut(doc['text'])) for doc in self.documents]
            self.bm25 = BM25Okapi(tokenized_corpus)
        print(f"✅ 成功缓冲载入知识库: [{self.db_name}] | chunk数: {len(self.documents)}")


class RAGRetriever:
    """RAG 全局检索器"""
    def __init__(self, base_dir: str = "data/database", model_name: str = None):
        if not model_name:
            with(open(f"data\\config\\config.json", 'r', encoding='utf-8')) as f:
                json_config = json.load(f)
                model_name = json_config["embedding_model"]
        # 初始化时只加载大模型
        print(f"⏳ 正在启动 RAG 引擎，加载嵌入模型 {model_name}...")
        self.model = SentenceTransformer(model_name)
        self.base_dir = base_dir
        self.buffer_pool: Dict[str, VectorDB] = {}
    def _get_or_load_db(self, db_name: str) -> Optional[VectorDB]:
        if db_name not in self.buffer_pool:
            db_path = os.path.join(self.base_dir, db_name)
            if os.path.exists(db_path) and os.path.isdir(db_path):
                print(f"📦 正在将知识库 [{db_name}] 读入内存...")
                self.buffer_pool[db_name] = VectorDB(db_name, self.base_dir)
            else:
                return None
        return self.buffer_pool.get(db_name)

    def search(self, query: str, target_dbs: List[str], top_k: int = 5, candidate_k: int = 60, rrf_k: int = 60) -> List[
        Dict]:
        """RAG + 关键词混合得分排名检索方法"""
        if not target_dbs:
            return []
        query_embedding = self.model.encode([query], normalize_embeddings=True)
        tokenized_query = list(jieba.cut(query))
        global_dense_ranks = {}
        global_sparse_ranks = {}

        for db_name in target_dbs:
            # 走到这里才会真正去尝试加载目标库
            db = self._get_or_load_db(db_name)
            if not db or db.index is None or db.index.ntotal == 0:
                continue

            search_k = min(candidate_k, len(db.documents))

            distances, indices = db.index.search(np.array(query_embedding).astype('float32'), search_k)
            for i, idx in enumerate(indices[0]):
                if idx != -1: global_dense_ranks[(db_name, idx)] = distances[0][i]

            sparse_scores = np.array(db.bm25.get_scores(tokenized_query))
            sparse_indices = np.argsort(sparse_scores)[::-1][:search_k]
            for idx in sparse_indices:
                if sparse_scores[idx] > 0: global_sparse_ranks[(db_name, idx)] = sparse_scores[idx]

        dense_sorted = sorted(global_dense_ranks.keys(), key=lambda x: global_dense_ranks[x], reverse=True)
        sparse_sorted = sorted(global_sparse_ranks.keys(), key=lambda x: global_sparse_ranks[x], reverse=True)

        dense_rank_dict = {doc_id: rank + 1 for rank, doc_id in enumerate(dense_sorted)}
        sparse_rank_dict = {doc_id: rank + 1 for rank, doc_id in enumerate(sparse_sorted)}

        all_candidate_ids = set(dense_rank_dict.keys()).union(set(sparse_rank_dict.keys()))
        rrf_scores = {}
        for doc_id in all_candidate_ids:
            dense_score = 1.0 / (rrf_k + dense_rank_dict[doc_id]) if doc_id in dense_rank_dict else 0.0
            sparse_score = 1.0 / (rrf_k + sparse_rank_dict[doc_id]) if doc_id in sparse_rank_dict else 0.0
            rrf_scores[doc_id] = dense_score + sparse_score
        ranked_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)[:top_k]
        results = []
        for db_name, idx in ranked_ids:
            db = self.buffer_pool[db_name]
            results.append({
                "db_name": db_name,
                "text": db.documents[idx]["text"],
                "meta": db.documents[idx].get("meta", {}),
                "rrf_score": round(rrf_scores[(db_name, idx)], 4)
            })
        return results
    def expand_context(self, db_name: str, source: str, center_chunk_id: int, window: int = 1) -> str:
        """由 chunk_id 检索上下文"""
        db = self._get_or_load_db(db_name)
        if not db:
            return ""
        expanded_texts = []
        for offset in range(-window, window + 1):
            target_id = center_chunk_id + offset
            text = db.doc_lookup.get((source, target_id))
            if text:
                expanded_texts.append(text)
        return "\n...\n".join(expanded_texts)

if __name__ == "__main__":
    # test
    target_databases = ["demo"]
    retriever = RAGRetriever(db_names=target_databases, base_dir="../../data/database")
    query_str = "AI在医疗领域有哪些具体的应用？"
    print(f"\n🔍 正在检索: {query_str}")
    results = retriever.search(query=query_str, top_k=3)
    print(results)
